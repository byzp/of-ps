from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    DungeonTaskFinishRewardReq,
    DungeonTaskFinishRewardRsp,
    StatusCode,
    DungeonData,
    RewardStatus,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils import item_mgr
from utils.reward_resolver import resolve_drop


@packet_handler(MsgId.DungeonTaskFinishRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonTaskFinishRewardReq()
        req.ParseFromString(data)

        rsp = DungeonTaskFinishRewardRsp()
        rsp.status = StatusCode.StatusCode_OK

        # dungeon_id=0 时 db.get_dungeon 会返回 dict 而非 bytes, 先拒绝
        if not req.dungeon_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.DungeonTaskFinishRewardRsp, rsp, packet_id)  # 1343,1344
            return

        # 领取副本全任务完成奖励, 用 DungeonData.task_finish_reward 去重
        dg = DungeonData()
        blob = db.get_dungeon(session.player_id, req.dungeon_id)
        if blob:
            dg.ParseFromString(blob)
        dg.dungeon_id = req.dungeon_id

        if dg.task_finish_reward == RewardStatus.Reward:
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.DungeonTaskFinishRewardRsp, rsp, packet_id)
            return

        dg.task_finish_reward = RewardStatus.Reward
        db.set_dungeon(session.player_id, req.dungeon_id, dg.SerializeToString())

        # 全任务完成奖励: Dungeon.json dungeon.reward_i_d -> Reward.json 解析。
        # 该字段是副本唯一的奖励配置(dungeon_quest 仅引用 Achieve 条件无奖励,
        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK
        reward_id = 0
        for e in res.get("Dungeon", {}).get("dungeon", {}).get("datas", ()):
            if e.get("i_d") == req.dungeon_id:
                reward_id = e.get("reward_i_d", 0)
                break
        if reward_id:
            player_level = db.get_players_info(session.player_id, "level")[0]
            world_level = db.get_players_info(session.player_id, "world_level")[0]
            items_list = resolve_drop(reward_id, world_level, player_level)
            item_mgr.grant_items(
                session.player_id,
                items_list,
                rsp_items=rsp.rewards,
                pack_notice=notice,
                session=session,
            )
        else:
            item_mgr.grant_items(
                session.player_id,
                [(101, 100)],
                rsp_items=rsp.rewards,
                pack_notice=notice,
                session=session,
            )

        session.send(MsgId.DungeonTaskFinishRewardRsp, rsp, packet_id)  # 1343,1344
        session.send(MsgId.PackNotice, notice, 0)  # 1400
