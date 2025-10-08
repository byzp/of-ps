from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetArchiveInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.req2685)
class GetArchiveInfoHandler(PacketHandler):
    def handle(self, session, data: bytes):
        rsp = GetArchiveInfoRsp_pb2.GetArchiveInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_Ok
        session.send(CmdId.rsp2686, rsp)
        