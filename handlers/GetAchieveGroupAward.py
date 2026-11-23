from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GetAchieveGroupAwardReq, GetAchieveGroupAwardRsp, StatusCode

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.reward_resolver import resolve_reward

"""
# 成就分组领奖 1755 1756
分组奖励(已对表验证): AchieveQuest.achieve_quest{achieve_group_i_d, reward_i_d}
以 achieve_group_i_d 对应 req.group_id(即 achieve_quest_group.i_d),
reward_i_d -> Reward.reward_pool(如 group 60010000 -> reward 106 -> 招募券x1)。
领取状态持久化在 claimed_rewards 表(system='achieve_group'),
db.try_claim 原子去重, db.get_claimed 可取已领列表
"""


@packet_handler(MsgId.GetAchieveGroupAwardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetAchieveGroupAwardReq()
        req.ParseFromString(data)

        rsp = GetAchieveGroupAwardRsp()

        # AchieveQuest.achieve_quest: achieve_group_i_d -> 分组总奖励 reward_i_d
        reward_id = None
        for entry in (
            res.get("AchieveQuest", {}).get("achieve_quest", {}).get("datas") or ()
        ):
            if entry.get("achieve_group_i_d") == req.group_id:
                reward_id = entry.get("reward_i_d")
                break
        if reward_id is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GetAchieveGroupAwardRsp, rsp, packet_id)
            return

        # 原子去重(claimed_rewards 表持久化)
        if not db.try_claim(session.player_id, "achieve_group", req.group_id):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.GetAchieveGroupAwardRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        # 玩家等级供 resolve_reward 按等级过滤奖池
        row = db.get_players_info(session.player_id, "level")
        reward_list = resolve_reward(reward_id, row[0] if row else 0)
        item_mgr.grant_items(
            session.player_id, reward_list, rsp_items=rsp.rewards, session=session
        )

        session.send(MsgId.GetAchieveGroupAwardRsp, rsp, packet_id)  # 1755,1756
