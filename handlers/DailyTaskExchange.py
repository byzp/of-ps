from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as DailyTaskExchangeReq_pb2
import proto.OverField_pb2 as DailyTaskExchangeRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


logger = logging.getLogger(__name__)

"""
 #每日任务兑换 2602 2603
"""


@packet_handler(CmdId.DailyTaskExchangeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DailyTaskExchangeReq_pb2.DailyTaskExchangeReq()
        req.ParseFromString(data)

        rsp = DailyTaskExchangeRsp_pb2.DailyTaskExchangeRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set fields from hardcoded test data
        rsp.today_converted = TEST_DATA["today_converted"]
        rsp.exchange_times_left = TEST_DATA["exchange_times_left"]

        for reward_data in TEST_DATA["rewards"]:
            reward_detail = rsp.rewards.add()
            reward_detail.main_item.item_id = reward_data["main_item"]["item_id"]
            reward_detail.main_item.item_tag = reward_data["main_item"]["item_tag"]
            reward_detail.main_item.is_new = reward_data["main_item"]["is_new"]
            reward_detail.main_item.temp_pack_index = reward_data["main_item"][
                "temp_pack_index"
            ]

            # Set base item for main item
            reward_detail.main_item.base_item.item_id = reward_data["main_item"][
                "base_item"
            ]["item_id"]
            reward_detail.main_item.base_item.num = reward_data["main_item"][
                "base_item"
            ]["num"]

        session.send(CmdId.DailyTaskExchangeRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "rewards": [
        {
            "main_item": {
                "item_id": 125,
                "item_tag": 9,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 125, "num": 1},
            }
        }
    ],
    "today_converted": 3,
    "exchange_times_left": 0,
}
