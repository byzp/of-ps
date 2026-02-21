from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import PosterIllustrationListRsp, StatusCode


@packet_handler(MsgId.PosterIllustrationListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = PosterIllustrationListRsp()
        rsp.status = StatusCode.StatusCode_OK

        session.send(MsgId.PosterIllustrationListRsp, rsp, packet_id)  # 1423,1424
