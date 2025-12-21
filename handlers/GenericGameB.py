from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GenericGameBRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GenericGameBReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GenericGameBRsp_pb2.GenericGameBRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK  # TODO
        session.send(MsgId.GenericGameBReq, rsp, packet_id)  # 2303,2304
