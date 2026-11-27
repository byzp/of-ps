from config import Config
from google.protobuf.message import DecodeError
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TreasureBoxPickupReq,
    TreasureBoxPickupRsp,
    StatusCode,
    TreasureBoxData,
    PackNotice,
    TreasureBoxState_Open,
    TREASURE_BOX_TYPE_DYNAMIC,
    TREASURE_BOX_TYPE_STATIC,
    TreasureBoxLocType_SCENE,
    TreasureBoxLocType_DUNGEON,
)
import utils.db as db
from utils import item_mgr, dungeon_state
from utils import treasure_box as tb_idx
from utils.dungeon_reward import material_dungeon


@packet_handler(MsgId.TreasureBoxPickupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with (
            item_mgr.player_lock(session.player_id),
            dungeon_state.player_lock(session.player_id),
            tb_idx.player_box_lock(session.player_id),
        ):
            self._handle(session, data, packet_id)

    def _handle(self, session, data, packet_id):
        req = TreasureBoxPickupReq()
        req.ParseFromString(data)
        rsp = TreasureBoxPickupRsp()
        if (
            req.box_type not in (TREASURE_BOX_TYPE_STATIC, TREASURE_BOX_TYPE_DYNAMIC)
            or req.loc_type not in (TreasureBoxLocType_SCENE, TreasureBoxLocType_DUNGEON)
            or req.pick_index < -1
        ):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
            return
        try:
            pack = self._pickup(session, req, rsp)
        except (
            DecodeError,
            item_mgr.EconomyConfigError,
            KeyError,
            IndexError,
            LookupError,
            TypeError,
            ValueError,
        ):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.items[:]
            session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
            return
        session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)

    def _pickup(self, session, req, rsp):
        resolved = tb_idx.resolve(session, req.box_type, req.box_index, req.loc_type)
        if resolved is None:
            rsp.status = StatusCode.StatusCode_TREASURE_BOX_NOT_EXIST
            return
        store_key, cfg_id = resolved
        tb_b, _ = tb_idx.load_record(session.player_id, store_key, req.box_index)
        if not tb_b:
            rsp.status = StatusCode.StatusCode_TREASURE_BOX_NOT_EXIST
            return
        tb = TreasureBoxData()
        tb.ParseFromString(tb_b)
        if tb.box_id != cfg_id:
            raise item_mgr.EconomyConfigError("treasure box config mismatch")
        if req.pick_index == -1:
            slots = list(range(len(tb.rewards)))
        elif 1 <= req.pick_index <= len(tb.rewards):
            slots = [req.pick_index - 1]
        else:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            return
        if not slots:
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            return
        picks = [tb.rewards[slot] for slot in slots]
        for item in picks:
            item_mgr.validate_pickup_item(item)
        instances = sum(item_mgr.needs_temp_pack(item) for item in picks)
        if len(session.temp_pack) + instances > Config.TEMP_PACK_MAX:
            rsp.status = StatusCode.StatusCode_Temp_Pack_Is_Full
            return

        cfg = (
            material_dungeon(session, req.loc_type)
            if req.box_type == TREASURE_BOX_TYPE_STATIC
            else None
        )
        paid = False
        cost = None
        if (
            cfg
            and cfg.get("new_consumption_mode") == Config.DUNGEON_BOX_CONSUMPTION_MODE
        ):
            paid = bool(item_mgr.validate_counter(
                int(db.get_kv(session.player_id, "dungeon_box_paid", store_key, 0) or 0),
                label="dungeon box paid marker",
            ))
            if not paid:
                cost_item = cfg.get("item_i_d", 0)
                item_mgr.validate_stackable_item_id(cost_item)
                multiple = item_mgr.validate_count(
                    int(db.get_kv(
                        session.player_id,
                        "dungeon_box_multiple",
                        store_key,
                        1,
                    ) or 0),
                    label="dungeon reward multiplier",
                )
                if multiple not in Config.DUNGEON_REWARD_MULTIPLIERS:
                    raise item_mgr.EconomyConfigError("invalid dungeon multiplier")
                cost_count = item_mgr.checked_mul(
                    item_mgr.validate_count(
                        cfg.get("item_num", 0), label="dungeon box cost"
                    ),
                    multiple,
                )
                cost = (cost_item, cost_count)

        pack = PackNotice(status=StatusCode.StatusCode_OK)
        staged_temp_pack = []
        with item_mgr.deferred_notifications(), db.transaction():
            if cost and not item_mgr.consume_items(
                session.player_id, [cost], pack_notice=pack, session=session
            ):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                return
            item_mgr.pickup_rewards(
                session,
                picks,
                rsp.items,
                pack,
                staged_temp_pack=staged_temp_pack,
            )
            if cost:
                # 与扣费同一事务; 保存失败时扣费、物品和奖励删除一起回滚。
                db.set_kv(session.player_id, "dungeon_box_paid", store_key, 1)
            if req.pick_index == -1:
                tb.ClearField("rewards")
            else:
                del tb.rewards[req.pick_index - 1]
            tb.state = TreasureBoxState_Open
            db.set_treasure_box(
                session.player_id, store_key, tb.SerializeToString()
            )
            rsp.status = StatusCode.StatusCode_OK

        # 提交后才发布会话临时背包, 避免失败后出现"背包有物、宝箱仍有奖励"。
        session.temp_pack.extend(staged_temp_pack)
        return pack
