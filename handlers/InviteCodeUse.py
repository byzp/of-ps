import datetime
import logging
import time

from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import InviteCodeUseReq, InviteCodeUseRsp, StatusCode, PackNotice
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


def _active_invite_activity(now):
    rows = res.get("Activity", {}).get("activity", {}).get("datas", ())
    for row in rows:
        # EActivityType_Invite (the legacy 6001/6002 invite activities).
        if row.get("new_activity_type") != 8:
            continue
        activity_id = row.get("i_d")
        if type(activity_id) is int and _activity_window(activity_id, now) is not None:
            return activity_id
    return None


def _invite_code_rewards(activity_id):
    rows = res.get("ActivityInvite", {}).get("activity_invite", {}).get("datas", ())
    row = next((item for item in rows if item.get("i_d") == activity_id), None)
    if row is None:
        return Config.INVITE_CODE_REWARDS_FALLBACK
    rewards = [
        (item["item_i_d"], item.get("item_num", 0))
        for item in row.get("activity_invite_item", ())
        if item.get("item_i_d") and item.get("item_num", 0) > 0
    ]
    return rewards or Config.INVITE_CODE_REWARDS_FALLBACK


@packet_handler(MsgId.InviteCodeUseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = InviteCodeUseReq()
        req.ParseFromString(data)

        rsp = InviteCodeUseRsp()
        now = int(time.time())
        activity_id = _active_invite_activity(now)
        if activity_id is None:
            rsp.status = StatusCode.StatusCode_ACTIVITY_INVITE_NOT_OPEN
            session.send(MsgId.InviteCodeUseRsp, rsp, packet_id)
            return

        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            status, _owner = redemption.use_invite_code(
                session.player_id, req.code, _invite_code_rewards(activity_id), rsp.rewards, pack
            )
        except Exception:
            logger.exception("Invite-code fulfillment failed")
            rsp.status = StatusCode.StatusCode_SYS_ERR
            session.send(MsgId.InviteCodeUseRsp, rsp, packet_id)
            return

        status_map = {
            "ok": StatusCode.StatusCode_OK,
            "invalid_code": StatusCode.StatusCode_INVITE_CODE_NOT_EXIST,
            "invalid_rewards": StatusCode.StatusCode_CFG_NOT_FOUND,
            "not_found": StatusCode.StatusCode_INVITE_CODE_NOT_EXIST,
            "already_filled": StatusCode.StatusCode_INVITE_CODE_ALREADY_FILLED,
            "cycle": StatusCode.StatusCode_INVITE_CODE_ALREADY_FILLED,
            "self_invite": StatusCode.StatusCode_INVITE_CODE_IS_SELF,
        }
        rsp.status = status_map[status]
        session.send(MsgId.InviteCodeUseRsp, rsp, packet_id)
        if status == "ok" and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
