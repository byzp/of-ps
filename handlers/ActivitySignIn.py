from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivitySignInReq,
    ActivitySignInRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res
from utils import achieve_track, item_mgr
from utils.activity_state import template_id

"""
# 活动签到 1985 1986
奖励来源 ActivitySign.json activity_sign(i_d=活动 id):
activity_sign_item[{days, activity_sign_reward_item[{item_i_d, item_num}]}]
"""


def _sign_rewards(activity_id, day):
    """按活动 id 和签到天数取奖励 [(item_id, num)]; 配置缺失返回 None"""
    rows = res.get("ActivitySign", {}).get("activity_sign", {}).get("datas")
    if rows is None:
        return None
    for row in rows:
        if row.get("i_d") != template_id(activity_id):
            continue
        for it in row.get("activity_sign_item", ()):
            if it.get("days", 0) == day:
                return [
                    (r["item_i_d"], r.get("item_num", 0))
                    for r in it.get("activity_sign_reward_item", ())
                    if r.get("item_i_d") and r.get("item_num", 0) > 0
                ]
        return None  # 活动存在但该天无配置
    return None


@packet_handler(MsgId.ActivitySignInReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivitySignInReq()
        req.ParseFromString(data)

        rsp = ActivitySignInRsp()
        rsp.day = req.day

        rewards = _sign_rewards(req.activity_id, req.day)
        if rewards is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ActivitySignInRsp, rsp, packet_id)  # 1985,1986
            return

        rsp.status = StatusCode.StatusCode_OK

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        if not db.try_claim(
            session.player_id, "activity_sign", f"{req.activity_id}:{req.day}"
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.ActivitySignInRsp, rsp, packet_id)  # 1985,1986
            return
        # 按实际已领天数设置位图，非连续领取时也与登录恢复一致。
        rsp.reward_id = sum(
            1 << int(k.split(":")[1])
            for k in db.get_claimed(session.player_id, "activity_sign")
            if k.startswith(f"{req.activity_id}:")
        )
        with achieve_track.batch(session):
            item_mgr.grant_items(
                session.player_id,
                rewards,
                rsp_items=rsp.rewards,
                pack_notice=pack,
                session=session,
            )
            session.send(MsgId.ActivitySignInRsp, rsp, packet_id)
            session.send(MsgId.PackNotice, pack, 0)
