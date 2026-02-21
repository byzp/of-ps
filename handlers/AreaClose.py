from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import AreaCloseReq, AreaCloseRsp, StatusCode, AreaData

logger = logging.getLogger(__name__)


"""
# 区域关闭 1901 1902
"""


@packet_handler(MsgId.AreaCloseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaCloseReq()
        req.ParseFromString(data)

        rsp = AreaCloseRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        area_data = rsp.area
        area_data.area_id = req.area_id  # 从请求获取
        area_data.area_state = TEST_DATA["area_state"]
        area_data.level = TEST_DATA["level"]

        session.send(MsgId.AreaCloseRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "area_state": 1, "level": 5}
