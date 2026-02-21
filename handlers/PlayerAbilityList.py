from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import PlayerAbilityListRsp, StatusCode


@packet_handler(MsgId.PlayerAbilityListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):

        rsp = PlayerAbilityListRsp()
        rsp.status = StatusCode.StatusCode_OK

        session.send(MsgId.PlayerAbilityListRsp, rsp, packet_id)  # 1611,1612
