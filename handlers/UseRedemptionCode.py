import logging

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import UseRedemptionCodeReq, UseRedemptionCodeRsp, StatusCode, PackNotice
from server import redemption

logger = logging.getLogger(__name__)

_STATUS_MAP = {
    1: StatusCode.StatusCode_REDEMPTION_CODE_NOT_EXIST,
    2: StatusCode.StatusCode_REDEMPTION_CODE_NOT_EXIST,
    3: StatusCode.StatusCode_REDEMPTION_CODE_NUM_IS_MAX,
    4: StatusCode.StatusCode_REDEMPTION_CODE_USED,
    5: StatusCode.StatusCode_REDEMPTION_CODE_FAIL,
    6: StatusCode.StatusCode_REDEMPTION_CODE_FAIL,
}


@packet_handler(MsgId.UseRedemptionCodeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UseRedemptionCodeReq()
        req.ParseFromString(data)

        rsp = UseRedemptionCodeRsp()
        rsp.code = redemption.normalize_code(req.code)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            status, _rewards = redemption.redeem_code(
                session.player_id, req.code, rsp.rewards, pack
            )
        except Exception:
            # The redemption transaction has rolled back the use marker/counter.
            logger.exception("Redemption-code fulfillment failed")
            rsp.status = StatusCode.StatusCode_REDEMPTION_CODE_FAIL
            session.send(MsgId.UseRedemptionCodeRsp, rsp, packet_id)
            return

        if status != 0:
            rsp.status = _STATUS_MAP[status]
            session.send(MsgId.UseRedemptionCodeRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.UseRedemptionCodeRsp, rsp, packet_id)
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
