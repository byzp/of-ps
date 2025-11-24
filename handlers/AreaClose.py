from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as AreaCloseReq_pb2
import proto.OverField_pb2 as AreaCloseRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as AreaData_pb2

logger = logging.getLogger(__name__)


"""
# 区域关闭 1901 1902
"""


@packet_handler(CmdId.AreaCloseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaCloseReq_pb2.AreaCloseReq()
        req.ParseFromString(data)

        rsp = AreaCloseRsp_pb2.AreaCloseRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        area_data = rsp.area
        area_data.area_id = req.area_id  # 从请求获取
        area_data.area_state = TEST_DATA["area_state"]
        area_data.level = TEST_DATA["level"]

        session.send(CmdId.AreaCloseRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "area_state": 1, "level": 5}
