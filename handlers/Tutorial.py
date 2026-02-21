from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import TutorialRsp, TutorialReq, StatusCode


@packet_handler(MsgId.TutorialReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TutorialReq()
        req.ParseFromString(data)

        rsp = TutorialRsp()
        rsp.status = StatusCode.StatusCode_OK

        session.send(MsgId.TutorialRsp, rsp, packet_id)  # 1589,1590
