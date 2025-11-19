from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GachaReq_pb2
import proto.OverField_pb2 as GachaRsp_pb2

logger = logging.getLogger(__name__)


"""
# 招募 1445 1446
"""


@packet_handler(CmdId.GachaReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GachaReq_pb2.GachaReq()
        req.ParseFromString(data)

        rsp = GachaRsp_pb2.GachaRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # Create main items
        for main_item_data in TEST_DATA["main_items"]:
            item_detail = rsp.items.add()
            item_detail.main_item.item_id = main_item_data["item_id"]
            item_detail.main_item.item_tag = main_item_data["item_tag"]
            item_detail.main_item.is_new = main_item_data["is_new"]
            item_detail.main_item.temp_pack_index = main_item_data["temp_pack_index"]

            # Set base item for main item
            item_detail.main_item.base_item.item_id = main_item_data["base_item"][
                "item_id"
            ]
            item_detail.main_item.base_item.num = main_item_data["base_item"]["num"]

            # Set character if available
            if (
                "character" in main_item_data
                and "character_id" in main_item_data["character"]
            ):
                item_detail.main_item.character.character_id = main_item_data[
                    "character"
                ]["character_id"]

            # Set extra quality if available
            if "extra_quality" in main_item_data:
                item_detail.extra_quality = main_item_data["extra_quality"]

        # Set gacha info
        rsp.info.gacha_id = TEST_DATA["info"]["gacha_id"]
        rsp.info.gacha_times = TEST_DATA["info"]["gacha_times"]
        rsp.info.has_full_pick = TEST_DATA["info"]["has_full_pick"]
        rsp.info.is_free = TEST_DATA["info"]["is_free"]
        rsp.info.optional_up_item = TEST_DATA["info"]["optional_up_item"]
        rsp.info.optional_value = TEST_DATA["info"]["optional_value"]
        rsp.info.guarantee = TEST_DATA["info"]["guarantee"]

        session.send(CmdId.GachaRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "main_items": [
        {
            "item_id": 402002,  # 物品id/角色id
            "item_tag": 7,  # 标签
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 0},  # 其它字段没用到所以没添加
            "character": {
                "character_id": 402002,  # 角色id
            },
            "extra_quality": 4,  # 额外品质
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 1},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 1},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 1},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 1},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 1},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 1},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 1},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 1},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
        {
            "item_id": 402002,
            "item_tag": 7,
            "is_new": True,
            "temp_pack_index": 0,
            "base_item": {"item_id": 0, "num": 0},
            "character": {
                "character_id": 402002,
            },
            "extra_quality": 4,
        },
    ],
    "info": {
        "gacha_id": 3014,
        "gacha_times": 10,
        "has_full_pick": False,
        "is_free": False,
        "optional_up_item": 0,
        "optional_value": 0,
        "guarantee": 60,
    },
}
