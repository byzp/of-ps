from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GenericGameBRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GenericGameBReq)
class GetArchiveInfoHandler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GenericGameBRsp_pb2.GenericGameBRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(CmdId.GenericGameBReq, rsp) #2303,2304
        session.sbin(2304, bin["2304"], False, packet_id)
