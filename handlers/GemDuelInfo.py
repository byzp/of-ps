from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GemDuelInfoReq_pb2
import proto.OverField_pb2 as GemDuelInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GemDuelInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GemDuelInfoReq_pb2.GemDuelInfoReq()
        req.ParseFromString(data)

        rsp = GemDuelInfoRsp_pb2.GemDuelInfoRsp()  # TODO
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(MsgId.GemDuelInfoRsp, rsp, packet_id)
