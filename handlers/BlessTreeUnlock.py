from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as BlessTreeUnlockReq_pb2
import proto.OverField_pb2 as BlessTreeUnlockRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


logger = logging.getLogger(__name__)

"""
 #祈愿树解锁 2587 2588
"""


@packet_handler(CmdId.BlessTreeUnlockReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BlessTreeUnlockReq_pb2.BlessTreeUnlockReq()
        req.ParseFromString(data)

        rsp = BlessTreeUnlockRsp_pb2.BlessTreeUnlockRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set fields from hardcoded test data
        rsp.def_id = req.def_id
        rsp.tree_id = req.tree_id

        for reward_data in TEST_DATA["rewards"]:
            reward_detail = rsp.rewards.add()

            # Set main item
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

        session.send(CmdId.BlessTreeUnlockRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "def_id": 20001,
    "tree_id": 11,
    "rewards": [
        {
            "main_item": {
                "item_id": 5054001,
                "item_tag": 8,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 5054001, "num": 1},
            }
        }
    ],
}
