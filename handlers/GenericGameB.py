from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import GenericGameBRsp, StatusCode


@packet_handler(MsgId.GenericGameBReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GenericGameBRsp()
        rsp.status = StatusCode.StatusCode_OK  # TODO
        session.send(MsgId.GenericGameBRsp, rsp, packet_id)  # 2303,2304
