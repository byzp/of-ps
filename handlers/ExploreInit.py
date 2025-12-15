from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as ExploreInitReq_pb2
import proto.OverField_pb2 as ExploreInitRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 探索初始化 1819 1820
"""


@packet_handler(MsgId.ExploreInitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreInitReq_pb2.ExploreInitReq()
        req.ParseFromString(data)

        rsp = ExploreInitRsp_pb2.ExploreInitRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # Set explore data
        for explore_data in TEST_DATA["explore"]:
            explore = rsp.explore.add()
            explore.explore_id = explore_data["explore_id"]
            explore.times = explore_data["times"]
            explore.start_time = explore_data["start_time"]
            explore.is_quick_finish = explore_data["is_quick_finish"]

            # Set collect_item_id
            for item_id in explore_data["collect_item_id"]:
                explore.collect_item_id.append(item_id)

            explore.collect_reward = explore_data["collect_reward"]

        # Set activity_explore (empty list in this case)
        # for activity_data in TEST_DATA["activity_explore"]:
        #     activity = rsp.activity_explore.add()
        #     # Add activity fields here if needed

        session.send(MsgId.ExploreInitRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "explore": [
        {
            "explore_id": 10102,
            "times": 0,
            "start_time": 0,
            "is_quick_finish": False,
            "collect_item_id": [2070, 101, 2020, 10],
            "collect_reward": True,
        },
        {
            "explore_id": 10301,
            "times": 0,
            "start_time": 0,
            "is_quick_finish": False,
            "collect_item_id": [481, 101, 10, 102, 491],
            "collect_reward": True,
        },
        {
            "explore_id": 10201,
            "times": 0,
            "start_time": 0,
            "is_quick_finish": False,
            "collect_item_id": [2020, 101, 401, 481, 102],
            "collect_reward": True,
        },
        {
            "explore_id": 10101,
            "times": 0,
            "start_time": 0,
            "is_quick_finish": False,
            "collect_item_id": [101, 109],
            "collect_reward": True,
        },
        {
            "explore_id": 10202,
            "times": 0,
            "start_time": 0,
            "is_quick_finish": False,
            "collect_item_id": [191, 10, 491, 11, 2070],
            "collect_reward": True,
        },
    ],
    "activity_explore": [],
}
