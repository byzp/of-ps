from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as SupplyBoxRewardReq_pb2
import proto.OverField_pb2 as SupplyBoxRewardRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


logger = logging.getLogger(__name__)

"""
 #补给箱奖励 1893 1894 有问题不会弹出奖励
"""


@packet_handler(CmdId.SupplyBoxRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SupplyBoxRewardReq_pb2.SupplyBoxRewardReq()
        req.ParseFromString(data)

        rsp = SupplyBoxRewardRsp_pb2.SupplyBoxRewardRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set fields from hardcoded test data
        rsp.next_reward_time = TEST_DATA["next_reward_time"]

        for item_data in TEST_DATA["items"]:
            item_detail = rsp.items.add()
            item_detail.main_item.item_id = item_data["main_item"]["item_id"]
            item_detail.main_item.item_tag = item_data["main_item"]["item_tag"]
            item_detail.main_item.is_new = item_data["main_item"]["is_new"]
            item_detail.main_item.temp_pack_index = item_data["main_item"][
                "temp_pack_index"
            ]

            # Set base item for main item
            item_detail.main_item.base_item.item_id = item_data["main_item"][
                "base_item"
            ]["item_id"]
            item_detail.main_item.base_item.num = item_data["main_item"]["base_item"][
                "num"
            ]

            item_detail.pack_type = item_data["pack_type"]

        session.send(CmdId.SupplyBoxRewardRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "next_reward_time": 1763353991,
    "items": [
        {
            "main_item": {
                "item_id": 101,
                "item_tag": 9,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 101, "num": 304},
            },  # 没用到的字段没有添加
            "pack_type": 2,
        },
        {
            "main_item": {
                "item_id": 102,
                "item_tag": 9,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 102, "num": 1},
            },
            "pack_type": 2,
        },
    ],
}
