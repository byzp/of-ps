from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import TakeOutFurnitureReq, TakeOutFurnitureRsp, StatusCode


@packet_handler(MsgId.TakeOutFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TakeOutFurnitureReq()
        req.ParseFromString(data)

        rsp = TakeOutFurnitureRsp()
        rsp.status = StatusCode.StatusCode_OK  # TODO 验证家具是否存在, 官服也没做这个
        rsp.furniture_id = req.furniture_id

        session.send(MsgId.TakeOutFurnitureRsp, rsp, packet_id)
