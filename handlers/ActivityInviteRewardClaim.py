from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityInviteRewardClaimReq,
    ActivityInviteRewardClaimRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res

"""
# 邀请活动任务领奖 2252 2253
配置来源 ActivityInvite.json:
activity_invite(i_d=活动 id).invitor_quest_group → activity_invite_quest 的
activity_invite_quest_pool_item[{achieve_i_d, complete_i_d,
activity_invite_pool_reward_item[{item_i_d, item_num}]}],
req.condition_id 匹配 achieve_i_d
"""


def _invite_quest_rewards(activity_id, condition_id):
    _tab = res.get("ActivityInvite")
    _tab = _tab if isinstance(_tab, dict) else {}
    _invites = (
        _tab.get("activity_invite", {}).get("datas")
        if isinstance(_tab.get("activity_invite"), dict)
        else None
    )
    _quests = (
        _tab.get("activity_invite_quest", {}).get("datas")
        if isinstance(_tab.get("activity_invite_quest"), dict)
        else None
    )
    if not isinstance(_invites, (list, tuple)) or not isinstance(
        _quests, (list, tuple)
    ):
        return None  # 资源缺失: 保持原 except 返回 None 的语义(调用方依赖)
    invites, quests = _invites, _quests
    group_id = None
    for row in invites:
        if row.get("i_d") == activity_id:
            group_id = row.get("invitor_quest_group")
            break
    if not group_id:
        return None
    for row in quests:
        if row.get("i_d") != group_id:
            continue
        for it in row.get("activity_invite_quest_pool_item", ()):
            if it.get("achieve_i_d") == condition_id:
                return [
                    (r["item_i_d"], r.get("item_num", 0))
                    for r in it.get("activity_invite_pool_reward_item", ())
                    if r.get("item_i_d") and r.get("item_num", 0) > 0
                ]
        return None
    return None


@packet_handler(MsgId.ActivityInviteRewardClaimReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityInviteRewardClaimReq()
        req.ParseFromString(data)

        rsp = ActivityInviteRewardClaimRsp()
        rsp.activity_id = req.activity_id
        rsp.condition_id = req.condition_id

        rewards = _invite_quest_rewards(req.activity_id, req.condition_id)
        if rewards is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(
                MsgId.ActivityInviteRewardClaimRsp, rsp, packet_id
            )  # 2252,2253
            return

        rsp.status = StatusCode.StatusCode_OK
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        if not db.try_claim(
            session.player_id,
            "activity_invite",
            f"{req.activity_id}:{req.condition_id}",
        ):
            rsp.status = StatusCode.StatusCode_ACTIVITY_INVITE_TASK_CLAIMED
            session.send(
                MsgId.ActivityInviteRewardClaimRsp, rsp, packet_id
            )  # 2252,2253
            return
        db.grant_rewards(session.player_id, rewards, rsp.rewards, pack)

        session.send(MsgId.ActivityInviteRewardClaimRsp, rsp, packet_id)  # 2252,2253
        session.send(MsgId.PackNotice, pack, 0)
