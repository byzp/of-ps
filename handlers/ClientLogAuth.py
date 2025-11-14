from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as ClientLogAuthRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(CmdId.ClientLogAuthReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = ClientLogAuthRsp_pb2.ClientLogAuthRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(CmdId.ClientLogAuthRsp, rsp, True, packet_id)  # 2201,2202
