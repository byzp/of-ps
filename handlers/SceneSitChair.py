from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as SceneSitChairReq_pb2
import proto.OverField_pb2 as SceneSitChairRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 场景坐椅子 1801 1802
"""


@packet_handler(MsgId.SceneSitChairReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SceneSitChairReq_pb2.SceneSitChairReq()
        req.ParseFromString(data)

        rsp = SceneSitChairRsp_pb2.SceneSitChairRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.player_id = session.player_id  # 从会话获取
        rsp.chair_id = req.chair_id  # 从请求获取
        rsp.seat_id = req.seat_id  # 从请求获取
        rsp.is_sit = req.is_sit  # 从请求获取

        session.send(MsgId.SceneSitChairRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
