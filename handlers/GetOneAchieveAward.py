from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetOneAchieveAwardReq,
    GetOneAchieveAwardRsp,
    StatusCode,
    PackNotice,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.reward_resolver import resolve_reward
from utils import achieve_track

"""
# 单个成就领奖 1759 1760
单条奖励(已对表验证): AchieveQuest.achieve_quest_group.achieve_quest_group_info
{achieve_condition_i_d, reward_i_d} 以 achieve_condition_i_d 对应 req.achieve_id,
reward_i_d -> Reward.reward_pool(如 achieve 60010011 -> reward 103 -> 星石x5)。
领取状态持久化在 claimed_rewards 表(system='achieve_one'),
db.try_claim 原子去重, db.get_claimed 可取已领列表
"""


@packet_handler(MsgId.GetOneAchieveAwardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetOneAchieveAwardReq()
        req.ParseFromString(data)

        rsp = GetOneAchieveAwardRsp()
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        achieve_track.sync_scoped_progress(session, (req.achieve_id,))
        achieve_b = db.get_achieve(session.player_id, req.achieve_id)
        if not achieve_b:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GetOneAchieveAwardRsp, rsp, packet_id)
            return
        target = achieve_track.target_of(req.achieve_id)
        if target is not None and achieve_track.progress(session.player_id, req.achieve_id) < target:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.GetOneAchieveAwardRsp, rsp, packet_id)
            return

        reward_id = None
        for group in res["AchieveQuest"]["achieve_quest_group"]["datas"]:
            if not isinstance(group, dict):
                continue
            for info in group.get("achieve_quest_group_info", ()):
                if not isinstance(info, dict):
                    continue
                if info.get("achieve_condition_i_d") == req.achieve_id:
                    reward_id = info.get("reward_i_d")
                    break
            if reward_id is not None:
                break
        if reward_id is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GetOneAchieveAwardRsp, rsp, packet_id)
            return

        level_row = db.get_players_info(session.player_id, "level")
        rewards = resolve_reward(reward_id, level_row[0] if level_row else 0)
        try:
            # 整批配置/数量先验证, 再进入 claim + 发奖事务。
            item_mgr.validate_rewards(rewards)
            with item_mgr.player_lock(session.player_id), item_mgr.deferred_notifications(), db.transaction():
                if not db.try_claim(session.player_id, "achieve_one", req.achieve_id):
                    rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                else:
                    item_mgr.grant_items(
                        session.player_id,
                        rewards,
                        rsp_items=rsp.rewards,
                        pack_notice=pack,
                        session=session,
                    )
                    rsp.status = StatusCode.StatusCode_OK
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.rewards[:]
            del pack.items[:]

        session.send(MsgId.GetOneAchieveAwardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
