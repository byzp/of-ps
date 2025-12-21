from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetAchieveGroupListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetAchieveGroupListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetAchieveGroupListRsp_pb2.GetAchieveGroupListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK  # TODO
        session.send(MsgId.GetAchieveGroupListRsp, rsp, packet_id)
