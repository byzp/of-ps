from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetLifeAchievementRewardReq,
    GetLifeAchievementRewardRsp,
    StatusCode,
)

import utils.db as db
from utils import item_mgr, achieve_track
from utils.reward_resolver import resolve_reward

"""
# 生活成就领奖 1387 1388
奖励登记(utils/achieve_track.life_reward_index):
Fishing.fishing_info / Make.make_item / Spin.spin_item / Handicraft.handicraft_item /
LifeGather.life_gather_item 各行 *achieve_rewards = {achieve_condition_i_d, reward_i_d},
目标次数取 Achieve.count_param; 进度为类型28(获取[item]xN)计数。
领取状态持久化 claimed_rewards(system=life_achieve), 原子去重。
"""


@packet_handler(MsgId.GetLifeAchievementRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetLifeAchievementRewardReq()
        req.ParseFromString(data)

        rsp = GetLifeAchievementRewardRsp()

        entry = achieve_track.life_reward_index().get(req.achieve_id)
        if not entry:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.GetLifeAchievementRewardRsp, rsp, packet_id)
            return
        reward_id, target = entry

        # 须已达成
        if achieve_track.progress(session.player_id, req.achieve_id) < target:
            rsp.status = StatusCode.StatusCode_FAIL  # 成就未达成
            session.send(MsgId.GetLifeAchievementRewardRsp, rsp, packet_id)
            return

        if not db.try_claim(session.player_id, "life_achieve", str(req.achieve_id)):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.GetLifeAchievementRewardRsp, rsp, packet_id)
            return

        row = db.get_players_info(session.player_id, "level")
        reward_list = resolve_reward(reward_id, row[0] if row else 0)
        item_mgr.grant_items(
            session.player_id, reward_list, session=session, rsp_items=rsp.items
        )

        rsp.status = StatusCode.StatusCode_OK
        rsp.rewarded_achieve_ids.append(req.achieve_id)
        session.send(MsgId.GetLifeAchievementRewardRsp, rsp, packet_id)  # 1387,1388
