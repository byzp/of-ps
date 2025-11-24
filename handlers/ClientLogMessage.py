from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as ClientLogMessageReq_pb2
import proto.OverField_pb2 as ClientLogMessageRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(CmdId.ClientLogMessageReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ClientLogMessageReq_pb2.ClientLogMessageReq()
        req.ParseFromString(data)

        rsp = ClientLogMessageRsp_pb2.ClientLogMessageRsp()
        rsp.ParseFromString(data)
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(CmdId.ClientLogMessageRsp, rsp, packet_id)  # 2203,2204
