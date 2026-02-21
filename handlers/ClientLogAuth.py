from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ClientLogAuthRsp, StatusCode


@packet_handler(MsgId.ClientLogAuthReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = ClientLogAuthRsp()
        rsp.status = StatusCode.StatusCode_OK

        session.send(MsgId.ClientLogAuthRsp, rsp, packet_id)  # 2201,2202
