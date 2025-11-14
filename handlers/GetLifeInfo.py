from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetLifeInfoReq_pb2
import proto.OverField_pb2 as GetLifeInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GetLifeInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetLifeInfoReq_pb2.GetLifeInfoReq()
        req.ParseFromString(data)

        rsp = GetLifeInfoRsp_pb2.GetLifeInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # session.send(CmdId.GetLifeInfoRsp, rsp) #1369,1370

        i = req.life_type
        if i == 1:
            session.sbin(1370, bin["1370-1"], False, packet_id)
        if i == 2:
            session.sbin(1370, bin["1370-2"], False, packet_id)
        if i == 3:
            session.sbin(1370, bin["1370-3"], False, packet_id)
        if i == 4:
            session.sbin(1370, bin["1370-4"], False, packet_id)
        if i == 5:
            session.sbin(1370, bin["1370-5"], False, packet_id)
        if i == 6:
            session.sbin(1370, bin["1370-6"], False, packet_id)
