from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import SceneProcessListRsp, StatusCode


@packet_handler(MsgId.SceneProcessListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SceneProcessListRsp()
        rsp.status = StatusCode.StatusCode_OK
        # TODO 地图探索度
        session.send(MsgId.SceneProcessListRsp, rsp, packet_id)  # 1871,1872
