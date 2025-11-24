from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as TreasureBoxOpenReq_pb2
import proto.OverField_pb2 as TreasureBoxOpenRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


logger = logging.getLogger(__name__)


@packet_handler(CmdId.TreasureBoxOpenReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureBoxOpenReq_pb2.TreasureBoxOpenReq()
        req.ParseFromString(data)

        rsp = TreasureBoxOpenRsp_pb2.TreasureBoxOpenRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set fields from hardcoded test data
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

            # Set armor if available
            if "armor" in item_data["main_item"]:
                armor_data = item_data["main_item"]["armor"]
                item_detail.main_item.armor.armor_id = armor_data["armor_id"]
                item_detail.main_item.armor.instance_id = armor_data["instance_id"]
                item_detail.main_item.armor.main_property_type = armor_data[
                    "main_property_type"
                ]
                item_detail.main_item.armor.main_property_val = armor_data[
                    "main_property_val"
                ]
                item_detail.main_item.armor.wearer_id = armor_data["wearer_id"]
                item_detail.main_item.armor.level = armor_data["level"]
                item_detail.main_item.armor.strength_level = armor_data[
                    "strength_level"
                ]
                item_detail.main_item.armor.strength_exp = armor_data["strength_exp"]
                item_detail.main_item.armor.property_index = armor_data[
                    "property_index"
                ]
                item_detail.main_item.armor.is_lock = armor_data["is_lock"]

            item_detail.pack_type = item_data["pack_type"]
            item_detail.extra_quality = item_data["extra_quality"]

        rsp.next_refresh_time = TEST_DATA["next_refresh_time"]

        session.send(CmdId.TreasureBoxOpenRsp, rsp, packet_id)


# Hardcoded test data from TreasureBoxOpenRsp.json
TEST_DATA = {
    "status": 1,
    "items": [
        {
            "main_item": {
                "item_id": 101,  # 物品id
                "item_tag": 9,  # 标签
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 101, "num": 90},
            },  # 没用到的字段没有添加
            "transformed_item": [],
            "extras": [],
            "pack_type": 2,
            "extra_quality": 0,
        },
        {
            "main_item": {
                "item_id": 2311007,
                "item_tag": 3,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 0, "num": 0},
                "armor": {
                    "armor_id": 2311007,
                    "instance_id": 25304,
                    "main_property_type": 41,
                    "main_property_val": 3,
                    "random_property": [],
                    "wearer_id": 0,
                    "level": 92,
                    "strength_level": 0,
                    "strength_exp": 0,
                    "property_index": 10,
                    "is_lock": False,
                },
            },
            "transformed_item": [],
            "extras": [],
            "pack_type": 2,
            "extra_quality": 0,
        },
        {
            "main_item": {
                "item_id": 3006,
                "item_tag": 8,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 3006, "num": 1},
            },
            "transformed_item": [],
            "extras": [],
            "pack_type": 2,
            "extra_quality": 0,
        },
    ],
    "next_refresh_time": 1763365177078,
}
