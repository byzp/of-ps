from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GardenPlaceCharacterReq_pb2
import proto.OverField_pb2 as GardenPlaceCharacterRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 放置角色到花园家具 2625 2626
"""


@packet_handler(CmdId.GardenPlaceCharacterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenPlaceCharacterReq_pb2.GardenPlaceCharacterReq()
        req.ParseFromString(data)

        rsp = GardenPlaceCharacterRsp_pb2.GardenPlaceCharacterRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.character_id = req.character_id  # 从请求获取
        rsp.furniture_id = req.furniture_id  # 从请求获取
        rsp.seat_id = req.seat_id  # 从请求获取
        rsp.is_remove = req.is_remove  # 从请求获取

        session.send(CmdId.GardenPlaceCharacterRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
