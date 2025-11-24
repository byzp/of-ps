from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as TakeOutFurnitureReq_pb2
import proto.OverField_pb2 as TakeOutFurnitureRsp_pb2


logger = logging.getLogger(__name__)


"""
# 取出家具 1683 1684
"""


@packet_handler(CmdId.TakeOutFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TakeOutFurnitureReq_pb2.TakeOutFurnitureReq()
        req.ParseFromString(data)

        rsp = TakeOutFurnitureRsp_pb2.TakeOutFurnitureRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.furniture_id = req.furniture_id  # 从请求获取

        session.send(CmdId.TakeOutFurnitureRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
