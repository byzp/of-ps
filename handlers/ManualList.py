from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ManualListRsp, StatusCode


@packet_handler(MsgId.ManualListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = ManualListRsp()
        rsp.status = StatusCode.StatusCode_OK
        # TODO
        session.send(MsgId.ManualListRsp, rsp, packet_id)  # 1861,1862
