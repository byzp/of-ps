from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as ClientLogAuthRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.ClientLogAuthReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = ClientLogAuthRsp_pb2.ClientLogAuthRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(MsgId.ClientLogAuthRsp, rsp, packet_id)  # 2201,2202
