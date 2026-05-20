from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import GetAchieveGroupListRsp, StatusCode


@packet_handler(MsgId.GetAchieveGroupListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetAchieveGroupListRsp()
        rsp.status = StatusCode.StatusCode_OK  # TODO
        session.send(MsgId.GetAchieveGroupListRsp, rsp, packet_id)
