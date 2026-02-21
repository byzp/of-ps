from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ClientLogMessageReq, ClientLogMessageRsp, StatusCode


@packet_handler(MsgId.ClientLogMessageReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ClientLogMessageReq()
        req.ParseFromString(data)

        rsp = ClientLogMessageRsp()
        rsp.ParseFromString(data)
        rsp.status = StatusCode.StatusCode_OK

        session.send(MsgId.ClientLogMessageRsp, rsp, packet_id)  # 2203,2204
