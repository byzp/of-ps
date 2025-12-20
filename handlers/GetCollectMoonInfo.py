from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetCollectMoonInfoReq_pb2
import proto.OverField_pb2 as GetCollectMoonInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetCollectMoonInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCollectMoonInfoReq_pb2.GetCollectMoonInfoReq()
        req.ParseFromString(data)

        rsp = GetCollectMoonInfoRsp_pb2.GetCollectMoonInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.scene_id = req.scene_id
        # TODO
        session.send(MsgId.GetCollectMoonInfoRsp, rsp, packet_id)
