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
from utils import achieve_track
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
        req = DungeonSweepReq()
        req.ParseFromString(data)

        rsp = DungeonSweepRsp()
        rsp.status = StatusCode.StatusCode_OK

        # dungeon_id=0 时 db.get_dungeon 会返回 dict 而非 bytes, 且会写入脏行, 先拒绝
        if not req.dungeon_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)  # 1353,1354
            return

        cfg = dungeon_config(req.dungeon_id)
        if not cfg:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)  # 1353,1354
            return
        if not prerequisite_finished(session.player_id, cfg):
            rsp.status = StatusCode.StatusCode_DungeonUnlock
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)
            return
        # Dungeon.json: 仅 is_can_sweep 的副本可扫荡
        if not cfg.get("is_can_sweep"):
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)  # 1353,1354
            return

        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK

        # 先解析奖励再扣费；展示表占位且无前置池时不允许空结算。
        details = None
        items = []
        multiple = (
            reward_multiplier(session.player_id, req.dungeon_id)
            if cfg.get("new_mission_type") == Config.MATERIAL_DUNGEON_TYPE
            else 1
        )
        if cfg.get("reward_i_d"):
            player_level = db.get_players_info(session.player_id, "level")[0]
            world_level = db.get_players_info(session.player_id, "world_level")[0]
            items = resolve_drop(cfg["reward_i_d"], world_level, player_level)
        else:
            details = make_dungeon_rewards(session.player_id, cfg, multiple)
        if not items and not details:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonSweepRsp, rsp, packet_id)
            return

        # 扫荡消耗按副本item_i_d x item_num；当前配置含20/30体力两档。
        cost_item = cfg.get("item_i_d", 0)
        cost_num = cfg.get("item_num", 0) * multiple
        if cost_item and cost_num:
            if not items_util.consume_items(
                session.player_id,
                [(cost_item, cost_num)],
                pack_notice=notice,
                session=session,
            ):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.DungeonSweepRsp, rsp, packet_id)  # 1353,1354
                return

        # 扫荡 = 不进本直接结算一次通关(参考 DungeonFinish 的通关记录路径)
        dg = DungeonData()
        blob = db.get_dungeon(session.player_id, req.dungeon_id)
        if blob:
            dg.ParseFromString(blob)
        dg.dungeon_id = req.dungeon_id
        dg.finish_times += 1
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

        session.send(MsgId.DungeonSweepRsp, rsp, packet_id)  # 1353,1354
        session.send(MsgId.PackNotice, notice, 0)  # 1400
        achieve_track.report(
            session,
            "dungeon_finish",
            match=req.dungeon_id,
            mission_type=cfg.get("new_mission_type"),
        )
