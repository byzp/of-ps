from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeNickNameReq_pb2
import proto.OverField_pb2 as ChangeNickNameRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 修改昵称 1527 1528
"""


@packet_handler(CmdId.ChangeNickNameReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeNickNameReq_pb2.ChangeNickNameReq()
        req.ParseFromString(data)

        rsp = ChangeNickNameRsp_pb2.ChangeNickNameRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set status from test data
        rsp.status = TEST_DATA["status"]
        
        # Set nick_name from request
        rsp.nick_name = req.nick_name

        # Set items from test data
        for item_data in TEST_DATA["items"]:
            item_detail = rsp.items.add()

            # Set main_item
            item_detail.main_item.item_id = item_data["main_item"]["item_id"]
            item_detail.main_item.item_tag = item_data["main_item"]["item_tag"]
            item_detail.main_item.is_new = item_data["main_item"]["is_new"]
            item_detail.main_item.temp_pack_index = item_data["main_item"][
                "temp_pack_index"
            ]

            # Set base_item
            item_detail.main_item.base_item.item_id = item_data["main_item"][
                "base_item"
            ]["item_id"]
            item_detail.main_item.base_item.num = item_data["main_item"]["base_item"][
                "num"
            ]

        session.send(CmdId.ChangeNickNameRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "items": [
        {
            "main_item": {
                "item_id": 102,
                "item_tag": 9,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 102, "num": 10832}
            }
        }
    ]
}