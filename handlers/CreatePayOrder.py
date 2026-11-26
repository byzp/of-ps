from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config
import logging

from proto.net_pb2 import CreatePayOrderReq, CreatePayOrderRsp, StatusCode
from server import payment_security

logger = logging.getLogger(__name__)


@packet_handler(MsgId.CreatePayOrderReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CreatePayOrderReq()
        req.ParseFromString(data)

        rsp = CreatePayOrderRsp()
        # Offline/local servers have no trusted payment provider or callback
        # route.  Even flipping REJECT_PAYMENT=False is not enough to opt in.
        if not payment_security.payment_is_enabled():
            rsp.status = StatusCode.StatusCode_Not_Payment
            rsp.result_str = "payment unavailable"
            payment_security.audit_best_effort(
                session.player_id, "payment_order", "rejected_unavailable"
            )
            session.send(MsgId.CreatePayOrderRsp, rsp, packet_id)
            return

        try:
            product = payment_security.resolve_product(
                req.shop_id, req.grid_id, req.pool_id
            )
            recipient = req.to_player_id or session.player_id
            order = payment_security.create_payment_order(
                session.player_id,
                recipient,
                product,
                getattr(Config, "PAYMENT_PRICES", {}),
                payment_security.callback_secret(),
            )
        except payment_security.PaymentError as error:
            payment_security.audit_best_effort(
                session.player_id, "payment_order", "rejected", reason=error.code
            )
            if error.code == "bad_request":
                rsp.status = StatusCode.StatusCode_BAD_REQ
            elif error.code == "rate_limited":
                rsp.status = StatusCode.StatusCode_CREATE_ORDER_SPEED_ERROR
            else:
                # Missing prices, secrets or provider configuration must never
                # be interpreted as a successful/simulated payment.
                rsp.status = StatusCode.StatusCode_Not_Payment
                logger.warning("Payment order unavailable: %s", error.code)
            rsp.result_str = "payment unavailable"
            session.send(MsgId.CreatePayOrderRsp, rsp, packet_id)
            return
        except Exception:
            payment_security.audit_best_effort(
                session.player_id, "payment_order", "rejected", reason="internal_error"
            )
            logger.exception("Could not create payment order")
            rsp.status = StatusCode.StatusCode_SYS_ERR
            session.send(MsgId.CreatePayOrderRsp, rsp, packet_id)
            return

        # Fulfillment belongs exclusively to the authenticated callback boundary.
        rsp.status = StatusCode.StatusCode_OK
        rsp.order_id = order["order_id"]
        rsp.result_str = "pending"
        session.send(MsgId.CreatePayOrderRsp, rsp, packet_id)
