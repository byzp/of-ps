from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import PlayerVitalityReq, PlayerVitalityRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.PlayerVitalityReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerVitalityReq()
        req.ParseFromString(data)

        rsp = PlayerVitalityRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.vitality_buy_num = 0  # TODO 体力购买限制

        session.send(MsgId.PlayerVitalityRsp, rsp, packet_id)
