from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GemDuelInfoReq, GemDuelInfoRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GemDuelInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GemDuelInfoReq()
        req.ParseFromString(data)

        rsp = GemDuelInfoRsp()  # TODO
        rsp.status = StatusCode.StatusCode_OK

        session.send(MsgId.GemDuelInfoRsp, rsp, packet_id)
