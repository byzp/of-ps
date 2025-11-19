from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as AreaUnlockReq_pb2
import proto.OverField_pb2 as AreaUnlockRsp_pb2


logger = logging.getLogger(__name__)


"""
# 区域解锁 1903 1904
"""


@packet_handler(CmdId.AreaUnlockReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaUnlockReq_pb2.AreaUnlockReq()
        req.ParseFromString(data)

        rsp = AreaUnlockRsp_pb2.AreaUnlockRsp()

        rsp.status = TEST_DATA["status"]
        
        # 创建区域数据
        area_data = rsp.area
        area_data.area_id = req.area_id  # 从请求获取area_id
        area_data.area_state = TEST_DATA["area_state"]
        area_data.level = TEST_DATA["level"]

        session.send(CmdId.AreaUnlockRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "area_state": 1, "level": 5}