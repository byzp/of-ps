from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as ManualListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin


@packet_handler(CmdId.ManualListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = ManualListRsp_pb2.ManualListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # session.send(CmdId.ManualListRsp, rsp) #1861,1862
        session.sbin(1862, bin["1862"], False, packet_id)
