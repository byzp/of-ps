from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import AbilityBadgeListRsp, StatusCode


@packet_handler(MsgId.AbilityBadgeListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = AbilityBadgeListRsp()
        rsp.status = StatusCode.StatusCode_OK
        # TODO
        session.send(MsgId.AbilityBadgeListRsp, rsp, packet_id)  # 1631,1632
