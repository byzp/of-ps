from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    TreasureBoxPickupReq,
    TreasureBoxPickupRsp,
    StatusCode,
    TreasureBoxData,
    PackNotice,
    TreasureBoxState_Open,
)
import utils.db as db
from utils import item_mgr, achieve_track, dungeon_state
from utils import treasure_box as tb_idx
from utils.dungeon_reward import material_dungeon


@packet_handler(MsgId.TreasureBoxPickupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with (
            dungeon_state.player_lock(session.player_id),
            tb_idx.player_box_lock(session.player_id),
        ):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = TreasureBoxPickupReq()
        req.ParseFromString(data)

        rsp = TreasureBoxPickupRsp()
        rsp.status = StatusCode.StatusCode_OK
        resolved = tb_idx.resolve(session, req.box_type, req.box_index, req.loc_type)
        store_key = resolved[0] if resolved is not None else None
        tb_b, _used_legacy = (
            tb_idx.load_record(session.player_id, store_key, req.box_index)
            if store_key is not None
            else (None, False)
        )
        tb = TreasureBoxData()
        if not tb_b:
            rsp.status = StatusCode.StatusCode_TREASURE_BOX_NOT_EXIST
            session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
            return
        tb.ParseFromString(tb_b)
        if req.pick_index == -1:
            picks = list(tb.rewards)
        elif 1 <= req.pick_index <= len(tb.rewards):
            picks = [tb.rewards[req.pick_index - 1]]
        else:
            picks = []
        inst_n = sum(item_mgr.needs_temp_pack(item) for item in picks)
        if len(session.temp_pack) + inst_n > Config.TEMP_PACK_MAX:
            rsp.status = StatusCode.StatusCode_Temp_Pack_Is_Full
            session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
            return
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        with achieve_track.batch(session):
            cfg = material_dungeon(session, req.loc_type) if req.box_type == 0 else None
            if (
                picks
                and cfg
                and cfg.get("new_consumption_mode")
                == Config.DUNGEON_BOX_CONSUMPTION_MODE
                and not db.get_kv(session.player_id, "dungeon_box_paid", store_key, 0)
            ):
                if not item_mgr.consume_items(
                    session.player_id,
                    [
                        (
                            cfg.get("item_i_d", 0),
                            cfg.get("item_num", 0)
                            * int(
                                db.get_kv(
                                    session.player_id,
                                    "dungeon_box_multiple",
                                    store_key,
                                    1,
                                )
                            ),
                        )
                    ],
                    pack_notice=rsp1,
                    session=session,
                ):
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
                    return
                db.set_kv(session.player_id, "dungeon_box_paid", store_key, 1)
            item_mgr.pickup_rewards(session, picks, rsp.items, rsp1)
            if req.pick_index == -1:
                tb.ClearField("rewards")
            elif 1 <= req.pick_index <= len(tb.rewards):
                del tb.rewards[req.pick_index - 1]
            tb.state = TreasureBoxState_Open
            db.set_treasure_box(session.player_id, store_key, tb.SerializeToString())
            session.send(MsgId.TreasureBoxPickupRsp, rsp, packet_id)
            if rsp1.items:
                session.send(MsgId.PackNotice, rsp1, 0)
