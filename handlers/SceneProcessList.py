from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as SceneProcessListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin


@packet_handler(MsgId.SceneProcessListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SceneProcessListRsp_pb2.SceneProcessListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # session.send(MsgId.SceneProcessListRsp, rsp) #1871,1872
        session.sbin(1872, bin["1872"], packet_id)
