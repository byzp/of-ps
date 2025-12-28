from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as TutorialRsp_pb2
import proto.OverField_pb2 as TutorialReq_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.TutorialReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TutorialReq_pb2.TutorialReq()
        req.ParseFromString(data)

        rsp = TutorialRsp_pb2.TutorialRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        session.send(MsgId.TutorialRsp, rsp, packet_id)  # 1589,1590
