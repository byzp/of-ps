from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import proto.OverField_pb2 as SceneProcessListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.SceneProcessListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SceneProcessListRsp_pb2.SceneProcessListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # TODO 地图探索度
        session.send(MsgId.SceneProcessListRsp, rsp, packet_id)  # 1871,1872
