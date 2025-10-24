from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetArchiveInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(2577)
class GetArchiveInfoHandler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetArchiveInfoRsp_pb2.GetArchiveInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(2578, rsp)
        session.sbin(2578, bin["2578"], False, packet_id)
