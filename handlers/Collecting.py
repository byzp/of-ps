from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CollectingReq_pb2
import proto.OverField_pb2 as CollectingRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 收集 1741 1742 场景物品收集

"""


@packet_handler(CmdId.CollectingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectingReq_pb2.CollectingReq()
        req.ParseFromString(data)

        rsp = CollectingRsp_pb2.CollectingRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        # 根据协议定义，collections和items是可选字段，这里使用空列表

        session.send(CmdId.CollectingRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
