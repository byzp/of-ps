from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import AreaAchieveListReq, AreaAchieveListRsp, StatusCode

logger = logging.getLogger(__name__)


"""
# 区域成就列表 1907 1908
"""


@packet_handler(MsgId.AreaAchieveListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaAchieveListReq()
        req.ParseFromString(data)

        rsp = AreaAchieveListRsp()

        rsp.status = TEST_DATA["status"]

        rsp.area_id = req.area_id  # 从请求获取area_id

        # 空的成就列表
        # rsp.achieves

        session.send(MsgId.AreaAchieveListRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
