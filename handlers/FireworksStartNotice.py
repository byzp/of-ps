from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import time

import proto.OverField_pb2 as FireworksStartNotice_pb2

logger = logging.getLogger(__name__)


"""
# 烟花开始通知 2160
"""


@packet_handler(CmdId.FireworksStartNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = FireworksStartNotice_pb2.FireworksStartNotice()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # Set fireworks info
        fireworks_info = rsp.fireworks_info
        fireworks_info.fireworks_id = TEST_DATA["fireworks_id"]
        fireworks_info.fireworks_duration_time = TEST_DATA["fireworks_duration_time"]
        fireworks_info.fireworks_start_time = int(time.time() * 1000)

        session.send(CmdId.FireworksStartNotice, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "fireworks_id": 10005,
    "fireworks_duration_time": 10000000,
}
