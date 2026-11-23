from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import IntervalRewardReq, IntervalRewardRsp, PackNotice, StatusCode
import utils.garden_state as garden_state
import utils.db as db

"""
# 领取好友间隙的奖励 1839 1840
奖励来源 Explore.json explore_interval:
- need_item_i_d: 奖励物品(全表均为 10)
- captain_count: 队长(间隙主人自己领, friend_id==player_id)数量
- member_count: 参与成员数量
"""


@packet_handler(MsgId.IntervalRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = IntervalRewardReq()
        req.ParseFromString(data)

        rsp = IntervalRewardRsp()
        rsp.friend_id = req.friend_id

        info = garden_state.get_interval(req.friend_id)
        member = None
        if info is not None:
            rsp.explore_id = info["interval_id"]
            for m in info["member"]:
                if m["player_id"] == session.player_id:
                    member = m
                    break
        else:
            rsp.explore_id = Config.DEFAULT_INTERVAL_ID

        if info is not None and info["finish_time"] > garden_state.now_ms():
            # 间隙尚未完成, 不能领奖
            rsp.status = StatusCode.StatusCode_INTERVAL_NOT_FINISH
            session.send(MsgId.IntervalRewardRsp, rsp, packet_id)  # 1839,1840
            return

        if member is not None and member["is_reward"]:
            # 已经领取过
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.IntervalRewardRsp, rsp, packet_id)  # 1839,1840
            return

        rsp.status = StatusCode.StatusCode_OK
        if member is not None:
            member["is_reward"] = True
            garden_state.set_interval(req.friend_id, info)

        # 发放奖励(explore_interval.need_item_i_d × captain_count/member_count)
        cfg = garden_state.interval_cfg(rsp.explore_id)
        if cfg and cfg.get("need_item_i_d"):
            reward_item = cfg["need_item_i_d"]
            if session.player_id == req.friend_id:
                reward_num = cfg.get("captain_count", 0)  # 领自己间隙 → 队长数量
            else:
                reward_num = cfg.get("member_count", 0)  # 帮好友 → 成员数量
        else:
            reward_item, reward_num = 10, 10

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        if reward_num > 0:
            gain, total = garden_state.grant_stack_item(
                session.player_id, reward_item, reward_num
            )
            rsp.rewards.add().CopyFrom(gain)
            pack.items.add().CopyFrom(total)

        session.send(MsgId.IntervalRewardRsp, rsp, packet_id)  # 1839,1840
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)  # 背包变化通知
