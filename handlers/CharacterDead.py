from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import CharacterDeadReq, CharacterDeadRsp, StatusCode


@packet_handler(MsgId.CharacterDeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterDeadReq()
        req.ParseFromString(data)

        rsp = CharacterDeadRsp()
        rsp.status = StatusCode.StatusCode_OK

        session.send(MsgId.CharacterDeadRsp, rsp, packet_id)
