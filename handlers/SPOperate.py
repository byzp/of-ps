import logging

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import SPOperateReq, SPOperateRsp, SPOperateType, StatusCode
from server import payment_security

logger = logging.getLogger(__name__)

_PASSWORD_PREFIX = "pbkdf2_sha256"


def _password_length():
    return payment_security.password_length()


def _hash_password(password):
    return payment_security.hash_password(password)


def _verify_password(stored, password):
    return payment_security.verify_password(stored, password)


_OPERATIONS = {
    SPOperateType.SPOperateType_Open: "open",
    SPOperateType.SPOperateType_Change: "change",
    SPOperateType.SPOperateType_Check: "check",
    SPOperateType.SPOperateType_Close: "close",
}


@packet_handler(MsgId.SPOperateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SPOperateReq()
        req.ParseFromString(data)

        rsp = SPOperateRsp(operate_type=req.operate_type, status=StatusCode.StatusCode_OK)
        operation = _OPERATIONS.get(req.operate_type)
        if operation is None:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.SPOperateRsp, rsp, packet_id)
            return

        try:
            ok, reason, state, verified_hash = payment_security.secondary_password_operation(
                session.player_id, operation, req.password, req.old_password
            )
        except payment_security.SecurityError:
            logger.exception("Secondary-password security state is unavailable")
            rsp.status = StatusCode.StatusCode_SYS_ERR
            session.send(MsgId.SPOperateRsp, rsp, packet_id)
            return
        except Exception:
            logger.exception("Secondary-password operation failed")
            rsp.status = StatusCode.StatusCode_SYS_ERR
            session.send(MsgId.SPOperateRsp, rsp, packet_id)
            return

        if ok and operation == "check" and verified_hash:
            # Sensitive account operations require an explicit recent Check;
            # setting or changing a password is not an authorization gesture.
            payment_security.record_verification(session, session.player_id, verified_hash)
        elif ok and operation == "close":
            session._ofps_sp_verified = None
        if not ok:
            # Do not distinguish wrong passwords from lockouts to clients.
            rsp.status = StatusCode.StatusCode_FAIL
            if reason == "locked":
                logger.info("Secondary-password lockout player_id=%s", session.player_id)
        rsp.sp_open_status = bool(state.get("open"))
        rsp.sp_check_status = bool(ok and (verified_hash or operation == "close"))
        session.send(MsgId.SPOperateRsp, rsp, packet_id)
