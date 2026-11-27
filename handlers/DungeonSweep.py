from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    DungeonSweepReq,
    DungeonSweepRsp,
    StatusCode,
    DungeonData,
    PackNotice,
)

import utils.db as db
from utils import item_mgr as items_util
from utils import achieve_track, dungeon_state
from utils.dungeon_reward import (
    dungeon_config,
    make_dungeon_rewards,
    prerequisite_finished,
    reward_multiplier,
)
from config import Config
from utils.reward_resolver import resolve_drop


@packet_handler(MsgId.DungeonSweepReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with dungeon_state.player_lock(session.player_id), items_util.player_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = DungeonSweepReq()
        req.ParseFromString(data)

        rsp = DungeonSweepRsp()
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        if not req.dungeon_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)
            return
        cfg = dungeon_config(req.dungeon_id)
        if not cfg:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)
            return
        if not prerequisite_finished(session.player_id, cfg):
            rsp.status = StatusCode.StatusCode_DungeonUnlock
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)
            return
        if not cfg.get("is_can_sweep"):
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)
            return

        try:
            multiple = items_util.validate_count(
                reward_multiplier(session.player_id, req.dungeon_id)
                if cfg.get("new_mission_type") == Config.MATERIAL_DUNGEON_TYPE
                else 1,
                label="dungeon reward multiplier",
            )
            cost_item = cfg.get("item_i_d", 0)
            per_cost = items_util.validate_count(
                cfg.get("item_num", 0), allow_zero=True, label="dungeon sweep cost"
            )
            cost_num = items_util.checked_mul(per_cost, multiple) if per_cost else 0
            if cost_item:
                items_util.validate_stackable_item_id(cost_item)

            # 先解析并验证奖励, 防止费用已扣后才发现奖励配置非法。
            details = None
            items = []
            if cfg.get("reward_i_d"):
                player_level = db.get_players_info(session.player_id, "level")[0]
                world_level = db.get_players_info(session.player_id, "world_level")[0]
                items = resolve_drop(cfg["reward_i_d"], world_level, player_level)
                items_util.validate_rewards(items)
            else:
                details = make_dungeon_rewards(session.player_id, cfg, multiple)
                for item in details:
                    items_util.validate_pickup_item(item)
            if not items and not details:
                raise items_util.EconomyConfigError("missing dungeon sweep reward")

            with items_util.deferred_notifications(), db.transaction():
                if cost_item and cost_num and not items_util.consume_items(
                    session.player_id,
                    [(cost_item, cost_num)],
                    pack_notice=notice,
                    session=session,
                ):
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                else:
                    dg = DungeonData()
                    blob = db.get_dungeon(session.player_id, req.dungeon_id)
                    if blob:
                        dg.ParseFromString(blob)
                    if dg.dungeon_id and dg.dungeon_id != req.dungeon_id:
                        raise items_util.EconomyConfigError("dungeon state id mismatch")
                    dg.dungeon_id = req.dungeon_id
                    dg.finish_times = items_util.checked_add(
                        items_util.validate_counter(
                            dg.finish_times, label="dungeon finish count"
                        ),
                        1,
                        limit=Config.ECONOMY_UINT32_MAX,
                    )
                    db.set_dungeon(session.player_id, req.dungeon_id, dg.SerializeToString())
                    if details is not None:
                        items_util.pickup_rewards(
                            session, details, rsp.rewards, notice, to_inventory=True
                        )
                    else:
                        items_util.grant_items(
                            session.player_id,
                            items,
                            rsp_items=rsp.rewards,
                            pack_notice=notice,
                            session=session,
                        )
                    rsp.status = StatusCode.StatusCode_OK
        except items_util.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.rewards[:]
            del notice.items[:]

        session.send(MsgId.DungeonSweepRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        achieve_track.report(
            session,
            "dungeon_finish",
            match=req.dungeon_id,
            mission_type=cfg.get("new_mission_type"),
        )
