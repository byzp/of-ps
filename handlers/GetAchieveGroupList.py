from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetAchieveGroupListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetAchieveGroupListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetAchieveGroupListRsp_pb2.GetAchieveGroupListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(MsgId.GetAchieveGroupListRsp, rsp, packet_id)
        # session.sbin(1758, bin["1758"],  packet_id)
