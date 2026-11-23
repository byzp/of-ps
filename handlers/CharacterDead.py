from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import CharacterDeadReq, CharacterDeadRsp, StatusCode

from utils import achieve_track


@packet_handler(MsgId.CharacterDeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterDeadReq()
        req.ParseFromString(data)

        rsp = CharacterDeadRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 成就: 丧失行动能力(第一次意外/熟练的观测者)
        achieve_track.report(session, "character_dead")

        session.send(MsgId.CharacterDeadRsp, rsp, packet_id)
