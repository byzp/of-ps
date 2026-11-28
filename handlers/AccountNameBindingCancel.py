import logging

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import AccountNameBindingCancelReq, AccountNameBindingCancelRsp, StatusCode
import utils.db as db
import server.photo_share as photo_share
from server import payment_security

logger = logging.getLogger(__name__)

_BINDING_NAMESPACE = "account_name_binding"


@packet_handler(MsgId.AccountNameBindingCancelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AccountNameBindingCancelReq()
        req.ParseFromString(data)

        rsp = AccountNameBindingCancelRsp()
        try:
            # The verification marker is session-bound and expires quickly; a
            # successful SPOperate/Check on another connection is not sufficient.
            with photo_share.lock_sp:
                with db.transaction():
                    if db.get_kv(session.player_id, _BINDING_NAMESPACE, "name") is None:
                        rsp.status = StatusCode.StatusCode_ACCOUNT_NAME_NOT_BIND
                    else:
                        state = payment_security.load_secondary_state(session.player_id)
                        if not payment_security.verification_is_current(session, state):
                            rsp.status = StatusCode.StatusCode_ACCOUNT_NAME_BIND_FAIL
                        else:
                            db.del_kv(session.player_id, _BINDING_NAMESPACE)
                            session._ofps_sp_verified = None
                            rsp.status = StatusCode.StatusCode_OK
                            rsp.player_id = session.player_id
                            payment_security.audit(
                                session.player_id, "account_name_binding_cancel", "fulfilled"
                            )
        except payment_security.SecurityError:
            logger.exception("Account binding security state is unavailable")
            rsp.status = StatusCode.StatusCode_SYS_ERR
        except Exception:
            logger.exception("Account name binding cancellation failed")
            rsp.status = StatusCode.StatusCode_SYS_ERR

        session.send(MsgId.AccountNameBindingCancelRsp, rsp, packet_id)
