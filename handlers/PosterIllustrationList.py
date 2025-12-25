from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as OverField_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.PosterIllustrationListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = OverField_pb2.PosterIllustrationListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(MsgId.PosterIllustrationListRsp, rsp, packet_id)  # 1423,1424
