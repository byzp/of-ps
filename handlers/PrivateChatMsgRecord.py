from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PrivateChatMsgRecordReq,
    PrivateChatMsgRecordRsp,
    StatusCode,
)


@packet_handler(MsgId.PrivateChatMsgRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PrivateChatMsgRecordReq()
        req.ParseFromString(data)

        rsp = PrivateChatMsgRecordRsp()
        rsp.status = StatusCode.StatusCode_OK  # TODO

        session.send(MsgId.PrivateChatMsgRecordRsp, rsp, packet_id)
