from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import AreaUnlockReq, AreaUnlockRsp


logger = logging.getLogger(__name__)


"""
# 区域解锁 1903 1904
"""


@packet_handler(MsgId.AreaUnlockReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaUnlockReq()
        req.ParseFromString(data)

        rsp = AreaUnlockRsp()

        rsp.status = TEST_DATA["status"]

        # 创建区域数据
        area_data = rsp.area
        area_data.area_id = req.area_id  # 从请求获取area_id
        area_data.area_state = TEST_DATA["area_state"]
        area_data.level = TEST_DATA["level"]

        session.send(MsgId.AreaUnlockRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "area_state": 1, "level": 5}
