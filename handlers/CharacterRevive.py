from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    CharacterReviveReq,
    CharacterReviveRsp,
    StatusCode,
)


@packet_handler(MsgId.CharacterReviveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterReviveReq()
        req.ParseFromString(data)

        rsp = CharacterReviveRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.CharacterReviveRsp, rsp, packet_id)
