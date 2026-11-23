from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityGiftRewardReq,
    ActivityGiftRewardRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res

"""
# 活动礼物领奖 2121 2122
奖励来源 ActivityGift.json activity_gift(i_d=活动 id):
activity_gift_item[{achieve_i_d, a_activity_gift_reward_item[{item_i_d, item_num}]}],
req.achieve_id 匹配 achieve_i_d
"""


def _gift_rewards(activity_id, achieve_id):
    rows = res.get("ActivityGift", {}).get("activity_gift", {}).get("datas")
    if rows is None:
        return None
    for row in rows:
        if row.get("i_d") != activity_id:
            continue
        for it in row.get("activity_gift_item", ()):
            if it.get("achieve_i_d") == achieve_id:
                return [
                    (r["item_i_d"], r.get("item_num", 0))
                    for r in it.get("a_activity_gift_reward_item", ())
                    if r.get("item_i_d") and r.get("item_num", 0) > 0
                ]
        return None
    return None


@packet_handler(MsgId.ActivityGiftRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityGiftRewardReq()
        req.ParseFromString(data)

        rsp = ActivityGiftRewardRsp()

        rewards = _gift_rewards(req.activity_id, req.achieve_id)
        if rewards is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ActivityGiftRewardRsp, rsp, packet_id)  # 2121,2122
            return

        rsp.status = StatusCode.StatusCode_OK
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        if not db.try_claim(
            session.player_id, "activity_gift", f"{req.activity_id}:{req.achieve_id}"
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.ActivityGiftRewardRsp, rsp, packet_id)  # 2121,2122
            return
        db.grant_rewards(session.player_id, rewards, rsp.rewards, pack)

        session.send(MsgId.ActivityGiftRewardRsp, rsp, packet_id)  # 2121,2122
        session.send(MsgId.PackNotice, pack, 0)
