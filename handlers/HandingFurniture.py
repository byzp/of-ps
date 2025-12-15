from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as HandingFurnitureReq_pb2
import proto.OverField_pb2 as HandingFurnitureRsp_pb2


logger = logging.getLogger(__name__)


"""
# 手持家具 2507 2508
"""


@packet_handler(MsgId.HandingFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = HandingFurnitureReq_pb2.HandingFurnitureReq()
        req.ParseFromString(data)

        rsp = HandingFurnitureRsp_pb2.HandingFurnitureRsp()

        rsp.status = TEST_DATA["status"]

        # 设置家具ID
        rsp.furniture_id = TEST_DATA["furniture_id"]

        session.send(MsgId.HandingFurnitureRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "furniture_id": 6274502690341576}
