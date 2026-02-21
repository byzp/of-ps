from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TakeOutHandingFurnitureReq,
    TakeOutHandingFurnitureRsp,
    StatusCode,
)


@packet_handler(MsgId.TakeOutHandingFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TakeOutHandingFurnitureReq()
        req.ParseFromString(data)

        rsp = TakeOutHandingFurnitureRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.furniture_id = req.furniture_id

        session.send(MsgId.TakeOutHandingFurnitureRsp, rsp, packet_id)
