from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GenericGameBRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GenericGameBReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GenericGameBRsp()
        rsp.status = StatusCode.StatusCode_OK  # TODO
        session.send(MsgId.GenericGameBReq, rsp, packet_id)  # 2303,2304
