import hashlib
import logging
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ReportReq, ReportRsp, StatusCode
import utils.db as db
from server import payment_security

logger = logging.getLogger(__name__)

_REPORT_MIN_INTERVAL_SECONDS = 5
_MAX_ROLE_NAME_LENGTH = 64
_MAX_REASON_LENGTH = 512
_MAX_CHAT_CONTENT_LENGTH = 2000


@packet_handler(MsgId.ReportReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ReportReq()
        req.ParseFromString(data)

        rsp = ReportRsp()
        if (
            req.reported_player_id <= 0
            or req.reported_player_id == session.player_id
            or not 0 <= req.report_status <= 8
            or not 0 <= req.chat_channel <= 7
        ):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ReportRsp, rsp, packet_id)
            return
        if (
            len(req.reported_role_name) > _MAX_ROLE_NAME_LENGTH
            or len(req.reason) > _MAX_REASON_LENGTH
            or len(req.chat_content) > _MAX_CHAT_CONTENT_LENGTH
        ):
            rsp.status = StatusCode.StatusCode_ILLEGAL_LEN
            session.send(MsgId.ReportRsp, rsp, packet_id)
            return

        try:
            with db.transaction():
                # Reported name/level are display data controlled by the client;
                # audit only the authoritative server-side player record.
                target = db.get_players_info(req.reported_player_id, "player_name,level")
                if not target:
                    rsp.status = StatusCode.StatusCode_PLAYER_NOT_FOUND
                else:
                    now = int(time.time())
                    last = db.get_kv(0, "report_rate", str(session.player_id), 0) or 0
                    if now - int(last) < _REPORT_MIN_INTERVAL_SECONDS:
                        rsp.status = StatusCode.StatusCode_REPORT_TIME_LIMIT
                    else:
                        db.set_kv(0, "report_rate", str(session.player_id), now)
                        server_name, server_level = target
                        # %r escapes newlines/control characters, preventing log
                        # injection.  Client-supplied identity fields are ignored.
                        logger.info(
                            "player_report reporter=%s report_status=%s chat_channel=%s "
                            "reported_player_id=%s reported_role_name=%r reported_role_level=%s "
                            "reason=%r chat_content=%r code=%s",
                            session.player_id, req.report_status, req.chat_channel,
                            req.reported_player_id, server_name, server_level,
                            req.reason[:_MAX_REASON_LENGTH],
                            req.chat_content[:_MAX_CHAT_CONTENT_LENGTH], req.code,
                        )
                        payment_security.audit(
                            session.player_id, "player_report", "accepted",
                            reported_player_id=req.reported_player_id,
                            report_status=req.report_status,
                            chat_content_hash=hashlib.sha256(req.chat_content.encode("utf-8")).hexdigest(),
                        )
                        rsp.status = StatusCode.StatusCode_OK
        except Exception:
            logger.exception("Player report could not be persisted")
            rsp.status = StatusCode.StatusCode_SYS_ERR

        session.send(MsgId.ReportRsp, rsp, packet_id)
