from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as MonsterDead_pb2

logger = logging.getLogger(__name__)


"""
# 怪物死亡 1851 1852
"""


@packet_handler(CmdId.MonsterDeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MonsterDead_pb2.MonsterDeadReq()
        req.ParseFromString(data)

        rsp = MonsterDead_pb2.MonsterDeadRsp()

        # 设置状态为成功
        rsp.status = TEST_DATA["status"]

        # 设置monster_index
        rsp.monster_index = TEST_DATA["monster_index"]

        # 设置drop_item数据
        rsp.drop_item.index = TEST_DATA["drop_item"]["index"]

        # 添加items到drop_item
        for item_data in TEST_DATA["drop_item"]["items"]:
            item = rsp.drop_item.items.add()

            # 设置main_item
            item.main_item.item_id = item_data["main_item"]["item_id"]
            item.main_item.item_tag = item_data["main_item"]["item_tag"]
            item.main_item.is_new = item_data["main_item"]["is_new"]
            item.main_item.temp_pack_index = item_data["main_item"]["temp_pack_index"]

            # 设置base_item
            item.main_item.base_item.item_id = item_data["main_item"]["base_item"][
                "item_id"
            ]
            item.main_item.base_item.num = item_data["main_item"]["base_item"]["num"]

            # 设置weapon
            weapon = item.main_item.weapon
            weapon.weapon_id = item_data["main_item"]["weapon"]["weapon_id"]
            weapon.instance_id = item_data["main_item"]["weapon"]["instance_id"]
            weapon.attack = item_data["main_item"]["weapon"]["attack"]
            weapon.damage_balance = item_data["main_item"]["weapon"]["damage_balance"]
            weapon.critical_ratio = item_data["main_item"]["weapon"]["critical_ratio"]
            # random_property是空数组，无需设置
            weapon.wearer_id = item_data["main_item"]["weapon"]["wearer_id"]
            weapon.level = item_data["main_item"]["weapon"]["level"]
            weapon.strength_level = item_data["main_item"]["weapon"]["strength_level"]
            weapon.strength_exp = item_data["main_item"]["weapon"]["strength_exp"]
            weapon.star = item_data["main_item"]["weapon"]["star"]
            weapon.inscription_1 = item_data["main_item"]["weapon"]["inscription_1"]
            weapon.durability = item_data["main_item"]["weapon"]["durability"]
            weapon.property_index = item_data["main_item"]["weapon"]["property_index"]
            weapon.is_lock = item_data["main_item"]["weapon"]["is_lock"]

            # armor、poster、character、outfit、inscription字段使用默认值（0或空）

            # 设置transformed_item为空数组
            # 设置extras为空数组

            # 设置pack_type和extra_quality
            item.pack_type = item_data["pack_type"]
            item.extra_quality = item_data["extra_quality"]

        session.send(CmdId.MonsterDeadRsp, rsp, False, packet_id)


# 硬编码测试数据
TEST_DATA = {
    "status": 1,
    "monster_index": 0,
    "drop_item": {
        "index": 28166,
        "items": [
            {
                "main_item": {
                    "item_id": 1401108,
                    "item_tag": 2,
                    "is_new": False,
                    "temp_pack_index": 0,
                    "base_item": {"item_id": 0, "num": 0},
                    "weapon": {
                        "weapon_id": 1401108,
                        "instance_id": 14807,
                        "attack": 24,
                        "damage_balance": 93,
                        "critical_ratio": 94,
                        "random_property": [],
                        "wearer_id": 0,
                        "level": 100,
                        "strength_level": 0,
                        "strength_exp": 0,
                        "star": 1,
                        "inscription_1": 0,
                        "durability": 0,
                        "property_index": 11,
                        "is_lock": False,
                    },
                    "armor": {
                        "armor_id": 0,
                        "instance_id": 0,
                        "main_property_type": 0,
                        "main_property_val": 0,
                        "random_property": [],
                        "wearer_id": 0,
                        "level": 0,
                        "strength_level": 0,
                        "strength_exp": 0,
                        "property_index": 0,
                        "is_lock": False,
                    },
                    "poster": {
                        "poster_id": 0,
                        "instance_id": 0,
                        "wearer_id": 0,
                        "star": 0,
                    },
                    "character": {
                        "character_id": 0,
                        "level": 0,
                        "max_level": 0,
                        "exp": 0,
                        "star": 0,
                        "equipment_presets": [],
                        "in_use_equipment_preset_index": 0,
                        "outfit_presets": [],
                        "in_use_outfit_preset_index": 0,
                        "gather_weapon": 0,
                        "character_appearance": {
                            "badge": 0,
                            "umbrella_id": 0,
                            "insect_net_instance_id": 0,
                            "logging_axe_instance_id": 0,
                            "water_bottle_instance_id": 0,
                            "mining_hammer_instance_id": 0,
                            "collection_gloves_instance_id": 0,
                            "fishing_rod_instance_id": 0,
                        },
                        "character_skill_list": [],
                        "rewarded_achievement_id_lst": [],
                        "is_unlock_payment": False,
                        "reward_index_lst": [],
                    },
                    "outfit": {"outfit_id": 0, "dye_schemes": []},
                    "inscription": {
                        "inscription_id": 0,
                        "level": 0,
                        "weapon_instance_id": 0,
                    },
                },
                "transformed_item": [],
                "extras": [],
                "pack_type": 2,
                "extra_quality": 0,
            }
        ],
    },
}
