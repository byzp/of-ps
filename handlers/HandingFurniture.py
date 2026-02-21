from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import random

from proto.net_pb2 import HandingFurnitureReq, HandingFurnitureRsp, StatusCode


@packet_handler(MsgId.HandingFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = HandingFurnitureReq()
        req.ParseFromString(data)

        rsp = HandingFurnitureRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.furniture_id = random.randint(10000000000000000, 99999999999999999)

        session.send(MsgId.HandingFurnitureRsp, rsp, packet_id)
