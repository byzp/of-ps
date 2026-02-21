from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GardenPlaceCharacterReq, GardenPlaceCharacterRsp, StatusCode

logger = logging.getLogger(__name__)


"""
# 放置角色到花园家具 2625 2626
"""


@packet_handler(MsgId.GardenPlaceCharacterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenPlaceCharacterReq()
        req.ParseFromString(data)

        rsp = GardenPlaceCharacterRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.character_id = req.character_id  # 从请求获取
        rsp.furniture_id = req.furniture_id  # 从请求获取
        rsp.seat_id = req.seat_id  # 从请求获取
        rsp.is_remove = req.is_remove  # 从请求获取

        session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
