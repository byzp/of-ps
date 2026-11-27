from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import IntervalRewardReq, IntervalRewardRsp, PackNotice, StatusCode
import utils.garden_state as garden_state
import utils.db as db
from utils import item_mgr

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
        if req.friend_id <= 0:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.IntervalRewardRsp, rsp, packet_id)
            return

        # The requested interval must exist and be complete. Missing state is not
        # an entitlement to the default interval's rewards.
        with item_mgr.player_lock(session.player_id), db.transaction():
            info = garden_state.get_interval(req.friend_id)
            if info is None or info["finish_time"] > garden_state.now_ms():
                rsp.status = StatusCode.StatusCode_INTERVAL_NOT_FINISH
                session.send(MsgId.IntervalRewardRsp, rsp, packet_id)
                return
            rsp.explore_id = info["interval_id"]
            is_owner = session.player_id == req.friend_id
            member = None
            if not is_owner:
                member = next(
                    (entry for entry in info["member"] if entry["player_id"] == session.player_id),
                    None,
                )
                if member is None:
                    rsp.status = StatusCode.StatusCode_INTERVAL_NOT_FINISH
                    session.send(MsgId.IntervalRewardRsp, rsp, packet_id)
                    return
                if member["is_reward"]:
                    rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                    session.send(MsgId.IntervalRewardRsp, rsp, packet_id)
                    return

            cfg = garden_state.interval_cfg(rsp.explore_id)
            reward_item = cfg.get("need_item_i_d") if cfg else None
            reward_num = cfg.get("captain_count" if is_owner else "member_count", 0) if cfg else 0
            if (
                type(reward_item) is not int or reward_item <= 0
                or type(reward_num) is not int or reward_num <= 0
            ):
                # Never fabricate a fallback item/count when authority is missing.
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.IntervalRewardRsp, rsp, packet_id)
                return

            claim_key = f"{req.friend_id}:{info['create_time']}"
            if is_owner and not db.try_claim(session.player_id, "interval_reward", claim_key):
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                session.send(MsgId.IntervalRewardRsp, rsp, packet_id)
                return

            rsp.status = StatusCode.StatusCode_OK
            if not is_owner:
                # Persist the member marker and grant in one transaction; a failed
                # grant must leave the reward claimable on retry.
                member["is_reward"] = True
                garden_state.set_interval(req.friend_id, info)
            gain, total = garden_state.grant_stack_item(
                session.player_id, reward_item, reward_num
            )
            rsp.rewards.add().CopyFrom(gain)
            pack = PackNotice(status=StatusCode.StatusCode_OK)
            pack.items.add().CopyFrom(total)

        session.send(MsgId.IntervalRewardRsp, rsp, packet_id)  # 1839,1840
        session.send(MsgId.PackNotice, pack, 0)  # 背包变化通知
