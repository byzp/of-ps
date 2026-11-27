import datetime
import logging
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ActivityInviteRewardClaimReq, ActivityInviteRewardClaimRsp, StatusCode, PackNotice
from server import redemption
from utils.res_loader import res

logger = logging.getLogger(__name__)


def _activity_window(activity_id, now):
    rows = res.get("Activity", {}).get("activity", {}).get("datas", ())
    row = next((item for item in rows if item.get("i_d") == activity_id), None)
    if row is None:
        return None
    try:
        start = (
            int(datetime.datetime.strptime(row["opening_time"], "%Y-%m-%d %H:%M:%S").timestamp())
            if row.get("opening_time") else 0
        )
        end = (
            int(datetime.datetime.strptime(row["closing_time"], "%Y-%m-%d %H:%M:%S").timestamp())
            if row.get("closing_time") else 0
        )
    except (KeyError, TypeError, ValueError):
        return None
    return (start, end) if start <= now and (not end or now <= end) else None


def _invite_quest_rule(activity_id, condition_id):
    table = res.get("ActivityInvite", {})
    invites = table.get("activity_invite", {}).get("datas", ())
    quests = table.get("activity_invite_quest", {}).get("datas", ())
    achieves = res.get("Achieve", {}).get("achieve", {}).get("datas", ())
    invite = next((row for row in invites if row.get("i_d") == activity_id), None)
    if invite is None or not invite.get("invitor_quest_group"):
        return None
    group_id = invite["invitor_quest_group"]
    quest = next((row for row in quests if row.get("i_d") == group_id), None)
    rule = next(
        (
            item
            for item in (quest or {}).get("activity_invite_quest_pool_item", ())
            if item.get("achieve_i_d") == condition_id
        ),
        None,
    )
    if rule is None:
        return None
    achieve = next((row for row in achieves if row.get("i_d") == condition_id), None)
    if achieve is None:
        return None
    try:
        required_count = int(achieve["count_param"])
    except (KeyError, TypeError, ValueError):
        return None
    predecessor_id = rule.get("complete_i_d", 0) or 0
    if type(predecessor_id) is not int or not 1 <= required_count <= 1000:
        return None
    rewards = [
        (item["item_i_d"], item.get("item_num", 0))
        for item in rule.get("activity_invite_pool_reward_item", ())
        if item.get("item_i_d") and item.get("item_num", 0) > 0
    ]
    if not rewards:
        return None
    return rewards, required_count, predecessor_id


@packet_handler(MsgId.ActivityInviteRewardClaimReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityInviteRewardClaimReq()
        req.ParseFromString(data)

        rsp = ActivityInviteRewardClaimRsp(
            activity_id=req.activity_id, condition_id=req.condition_id
        )
        if _activity_window(req.activity_id, int(time.time())) is None:
            rsp.status = StatusCode.StatusCode_ACTIVITY_INVITE_NOT_OPEN
            session.send(MsgId.ActivityInviteRewardClaimRsp, rsp, packet_id)
            return
        rule = _invite_quest_rule(req.activity_id, req.condition_id)
        if rule is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ActivityInviteRewardClaimRsp, rsp, packet_id)
            return
        rewards, required_count, predecessor_id = rule
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            status = redemption.claim_invite_reward(
                session.player_id, req.activity_id, req.condition_id, rewards,
                required_count, predecessor_id, rsp.rewards, pack,
            )
        except Exception:
            logger.exception("Invite reward fulfillment failed")
            rsp.status = StatusCode.StatusCode_SYS_ERR
            session.send(MsgId.ActivityInviteRewardClaimRsp, rsp, packet_id)
            return

        status_map = {
            "ok": StatusCode.StatusCode_OK,
            "not_completed": StatusCode.StatusCode_ACTIVITY_INVITE_TASK_NOT_COMPLETED,
            "already_claimed": StatusCode.StatusCode_ACTIVITY_INVITE_TASK_CLAIMED,
            "invalid_rewards": StatusCode.StatusCode_CFG_NOT_FOUND,
            "invalid_request": StatusCode.StatusCode_BAD_REQ,
        }
        rsp.status = status_map[status]
        session.send(MsgId.ActivityInviteRewardClaimRsp, rsp, packet_id)
        if status == "ok" and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
