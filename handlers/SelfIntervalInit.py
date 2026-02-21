from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import SelfIntervalInitReq, SelfIntervalInitRsp, StatusCode

logger = logging.getLogger(__name__)


"""
# 自身间隙初始化 1843 1844
"""


@packet_handler(MsgId.SelfIntervalInitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SelfIntervalInitReq()
        req.ParseFromString(data)

        rsp = SelfIntervalInitRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.interval_id = TEST_DATA["interval_id"]
        rsp.end_time = TEST_DATA["end_time"]
        rsp.is_start = TEST_DATA["is_start"]

        # Set interval data
        interval = rsp.interval
        interval.interval_id = TEST_DATA["interval"]["interval_id"]
        interval.finish_time = TEST_DATA["interval"]["finish_time"]
        interval.player_id = TEST_DATA["interval"]["player_id"]
        interval.create_time = TEST_DATA["interval"]["create_time"]

        # Set member (empty list in this case)
        # for member_data in TEST_DATA["interval"]["member"]:
        #     member = interval.member.add()
        #     # Add member fields here if needed

        session.send(MsgId.SelfIntervalInitRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "interval_id": 0,
    "end_time": 0,
    "is_start": False,
    "interval": {
        "interval_id": 0,
        "finish_time": 0,
        "player_id": 0,
        "create_time": 0,
        "member": [],
    },
}
