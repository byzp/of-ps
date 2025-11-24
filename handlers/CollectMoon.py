from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CollectMoonReq_pb2
import proto.OverField_pb2 as CollectMoonRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


logger = logging.getLogger(__name__)


@packet_handler(CmdId.CollectMoonReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectMoonReq_pb2.CollectMoonReq()
        req.ParseFromString(data)

        rsp = CollectMoonRsp_pb2.CollectMoonRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set moon_id from request
        rsp.moon_id = req.moon_id

        # Set fields from hardcoded test data
        for reward_data in TEST_DATA["rewards"]:
            reward = rsp.rewards.add()

            # Set main_item
            reward.main_item.item_id = reward_data["main_item"]["item_id"]
            reward.main_item.item_tag = reward_data["main_item"]["item_tag"]
            reward.main_item.is_new = reward_data["main_item"]["is_new"]
            reward.main_item.temp_pack_index = reward_data["main_item"][
                "temp_pack_index"
            ]

            # Set base_item
            reward.main_item.base_item.item_id = reward_data["main_item"]["base_item"][
                "item_id"
            ]
            reward.main_item.base_item.num = reward_data["main_item"]["base_item"][
                "num"
            ]

            # Set weapon
            weapon = reward.main_item.weapon
            weapon_data = reward_data["main_item"]["weapon"]
            weapon.weapon_id = weapon_data["weapon_id"]
            weapon.instance_id = weapon_data["instance_id"]
            weapon.attack = weapon_data["attack"]
            weapon.damage_balance = weapon_data["damage_balance"]
            weapon.critical_ratio = weapon_data["critical_ratio"]
            weapon.wearer_id = weapon_data["wearer_id"]
            weapon.level = weapon_data["level"]
            weapon.strength_level = weapon_data["strength_level"]
            weapon.strength_exp = weapon_data["strength_exp"]
            weapon.star = weapon_data["star"]
            weapon.inscription_1 = weapon_data["inscription_1"]
            weapon.durability = weapon_data["durability"]
            weapon.property_index = weapon_data["property_index"]
            weapon.is_lock = weapon_data["is_lock"]

            # Set armor
            armor = reward.main_item.armor
            armor_data = reward_data["main_item"]["armor"]
            armor.armor_id = armor_data["armor_id"]
            armor.instance_id = armor_data["instance_id"]
            armor.main_property_type = armor_data["main_property_type"]
            armor.main_property_val = armor_data["main_property_val"]
            armor.wearer_id = armor_data["wearer_id"]
            armor.level = armor_data["level"]
            armor.strength_level = armor_data["strength_level"]
            armor.strength_exp = armor_data["strength_exp"]
            armor.property_index = armor_data["property_index"]
            armor.is_lock = armor_data["is_lock"]

            # Set poster
            poster = reward.main_item.poster
            poster_data = reward_data["main_item"]["poster"]
            poster.poster_id = poster_data["poster_id"]
            poster.instance_id = poster_data["instance_id"]
            poster.wearer_id = poster_data["wearer_id"]
            poster.star = poster_data["star"]

            # Set character
            character = reward.main_item.character
            character_data = reward_data["main_item"]["character"]
            character.character_id = character_data["character_id"]
            character.level = character_data["level"]
            character.max_level = character_data["max_level"]
            character.exp = character_data["exp"]
            character.star = character_data["star"]
            character.in_use_equipment_preset_index = character_data[
                "in_use_equipment_preset_index"
            ]
            character.in_use_outfit_preset_index = character_data[
                "in_use_outfit_preset_index"
            ]
            character.gather_weapon = character_data["gather_weapon"]
            character.is_unlock_payment = character_data["is_unlock_payment"]

            # Set outfit
            outfit = reward.main_item.outfit
            outfit_data = reward_data["main_item"]["outfit"]
            outfit.outfit_id = outfit_data["outfit_id"]

            # Set inscription
            inscription = reward.main_item.inscription
            inscription_data = reward_data["main_item"]["inscription"]
            inscription.inscription_id = inscription_data["inscription_id"]
            inscription.level = inscription_data["level"]
            inscription.weapon_instance_id = inscription_data["weapon_instance_id"]

            # Set other fields
            reward.pack_type = reward_data["pack_type"]
            reward.extra_quality = reward_data["extra_quality"]

        session.send(CmdId.CollectMoonRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "moon_id": 11001002,
    "rewards": [
        {
            "main_item": {
                "item_id": 124,
                "item_tag": 9,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 124, "num": 5},
                "weapon": {
                    "weapon_id": 0,
                    "instance_id": 0,
                    "attack": 0,
                    "damage_balance": 0,
                    "critical_ratio": 0,
                    "random_property": [],
                    "wearer_id": 0,
                    "level": 0,
                    "strength_level": 0,
                    "strength_exp": 0,
                    "star": 0,
                    "inscription_1": 0,
                    "durability": 0,
                    "property_index": 0,
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
                "poster": {"poster_id": 0, "instance_id": 0, "wearer_id": 0, "star": 0},
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
            "pack_type": 0,
            "extra_quality": 0,
        }
    ],
}
