from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import random

import proto.OverField_pb2 as HandingFurnitureReq_pb2
import proto.OverField_pb2 as HandingFurnitureRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(MsgId.HandingFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = HandingFurnitureReq_pb2.HandingFurnitureReq()
        req.ParseFromString(data)

        rsp = HandingFurnitureRsp_pb2.HandingFurnitureRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.furniture_id = random.randint(10000000000000000, 99999999999999999)

        session.send(MsgId.HandingFurnitureRsp, rsp, packet_id)


