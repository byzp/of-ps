from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as TakeOutHandingFurnitureReq_pb2
import proto.OverField_pb2 as TakeOutHandingFurnitureRsp_pb2


logger = logging.getLogger(__name__)


"""
# 取出手持家具 2509 2510
"""


@packet_handler(MsgId.TakeOutHandingFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TakeOutHandingFurnitureReq_pb2.TakeOutHandingFurnitureReq()
        req.ParseFromString(data)

        rsp = TakeOutHandingFurnitureRsp_pb2.TakeOutHandingFurnitureRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.furniture_id = req.furniture_id  # 从请求获取

        session.send(MsgId.TakeOutHandingFurnitureRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
