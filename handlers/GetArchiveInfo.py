from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetArchiveInfoReq_pb2
import proto.OverField_pb2 as GetArchiveInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GetArchiveInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetArchiveInfoReq_pb2.GetArchiveInfoReq()
        req.ParseFromString(data)

        rsp = GetArchiveInfoRsp_pb2.GetArchiveInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(CmdId.GetArchiveInfoRsp, rsp) #1213,1214
        key = req.key
        if key == "BlessingTreeTutotal":
            session.sbin(1214, bin["1214-1"], False, packet_id)
            return
        if key == "FixOrFlolowMode":
            session.sbin(1214, bin["1214-2"], False, packet_id)
            return
        if key == "":
            session.sbin(1214, bin["1214-3"], False, packet_id)
            return
        if key == "ButtonModeState":
            session.sbin(1214, bin["1214-4"], False, packet_id)
            return
        session.sbin(1214, bin["1214-3"], False, packet_id)
