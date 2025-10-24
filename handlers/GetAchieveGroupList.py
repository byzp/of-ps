from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetAchieveGroupListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GetAchieveGroupListReq)
class GetArchiveInfoHandler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetAchieveGroupListRsp_pb2.GetAchieveGroupListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(CmdId.GenericGameBReq, rsp) #
        session.sbin(1758, bin["1758"], False, packet_id)
