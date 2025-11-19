from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ShopBuyReq_pb2
import proto.OverField_pb2 as ShopBuyRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ShopBuyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ShopBuyReq_pb2.ShopBuyReq()
        req.ParseFromString(data)

        rsp = ShopBuyRsp_pb2.ShopBuyRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set fields from hardcoded test data
        rsp.shop_id = TEST_DATA["shop_id"]
        rsp.grids.id = TEST_DATA["grids"]["id"]
        rsp.grids.grid_id = TEST_DATA["grids"]["grid_id"]
        rsp.grids.pool_id = TEST_DATA["grids"]["pool_id"]
        rsp.grids.pool_index = TEST_DATA["grids"]["pool_index"]
        rsp.grids.buy_times = TEST_DATA["grids"]["buy_times"]
        rsp.grids.update_time = TEST_DATA["grids"]["update_time"]

        # Add items from test data
        for item_data in TEST_DATA["items"]:
            item = rsp.items.add()
            item.main_item.item_id = item_data["main_item"]["item_id"]
            item.main_item.item_tag = item_data["main_item"]["item_tag"]
            item.main_item.is_new = item_data["main_item"]["is_new"]
            item.main_item.temp_pack_index = item_data["main_item"]["temp_pack_index"]

            # Set base item details
            item.main_item.base_item.item_id = item_data["main_item"]["base_item"][
                "item_id"
            ]
            item.main_item.base_item.num = item_data["main_item"]["base_item"]["num"]

            # Set weapon details (even if zeros)
            item.main_item.weapon.weapon_id = item_data["main_item"]["weapon"][
                "weapon_id"
            ]
            item.main_item.weapon.instance_id = item_data["main_item"]["weapon"][
                "instance_id"
            ]
            item.main_item.weapon.attack = item_data["main_item"]["weapon"]["attack"]
            item.main_item.weapon.damage_balance = item_data["main_item"]["weapon"][
                "damage_balance"
            ]
            item.main_item.weapon.critical_ratio = item_data["main_item"]["weapon"][
                "critical_ratio"
            ]
            item.main_item.weapon.wearer_id = item_data["main_item"]["weapon"][
                "wearer_id"
            ]
            item.main_item.weapon.level = item_data["main_item"]["weapon"]["level"]
            item.main_item.weapon.strength_level = item_data["main_item"]["weapon"][
                "strength_level"
            ]
            item.main_item.weapon.strength_exp = item_data["main_item"]["weapon"][
                "strength_exp"
            ]
            item.main_item.weapon.star = item_data["main_item"]["weapon"]["star"]
            item.main_item.weapon.inscription_1 = item_data["main_item"]["weapon"][
                "inscription_1"
            ]
            item.main_item.weapon.durability = item_data["main_item"]["weapon"][
                "durability"
            ]
            item.main_item.weapon.property_index = item_data["main_item"]["weapon"][
                "property_index"
            ]
            item.main_item.weapon.is_lock = item_data["main_item"]["weapon"]["is_lock"]

            # Set armor details (even if zeros)
            item.main_item.armor.armor_id = item_data["main_item"]["armor"]["armor_id"]
            item.main_item.armor.instance_id = item_data["main_item"]["armor"][
                "instance_id"
            ]
            item.main_item.armor.main_property_type = item_data["main_item"]["armor"][
                "main_property_type"
            ]
            item.main_item.armor.main_property_val = item_data["main_item"]["armor"][
                "main_property_val"
            ]
            item.main_item.armor.wearer_id = item_data["main_item"]["armor"][
                "wearer_id"
            ]
            item.main_item.armor.level = item_data["main_item"]["armor"]["level"]
            item.main_item.armor.strength_level = item_data["main_item"]["armor"][
                "strength_level"
            ]
            item.main_item.armor.strength_exp = item_data["main_item"]["armor"][
                "strength_exp"
            ]
            item.main_item.armor.property_index = item_data["main_item"]["armor"][
                "property_index"
            ]
            item.main_item.armor.is_lock = item_data["main_item"]["armor"]["is_lock"]

            # Set poster details (even if zeros)
            item.main_item.poster.poster_id = item_data["main_item"]["poster"][
                "poster_id"
            ]
            item.main_item.poster.instance_id = item_data["main_item"]["poster"][
                "instance_id"
            ]
            item.main_item.poster.wearer_id = item_data["main_item"]["poster"][
                "wearer_id"
            ]
            item.main_item.poster.star = item_data["main_item"]["poster"]["star"]

            # Set character details (even if zeros)
            item.main_item.character.character_id = item_data["main_item"]["character"][
                "character_id"
            ]
            item.main_item.character.level = item_data["main_item"]["character"][
                "level"
            ]
            item.main_item.character.max_level = item_data["main_item"]["character"][
                "max_level"
            ]
            item.main_item.character.exp = item_data["main_item"]["character"]["exp"]
            item.main_item.character.star = item_data["main_item"]["character"]["star"]
            item.main_item.character.is_unlock_payment = item_data["main_item"][
                "character"
            ]["is_unlock_payment"]

            # Set outfit details (even if zeros)
            item.main_item.outfit.outfit_id = item_data["main_item"]["outfit"][
                "outfit_id"
            ]

            # Set inscription details (even if zeros)
            item.main_item.inscription.inscription_id = item_data["main_item"][
                "inscription"
            ]["inscription_id"]
            item.main_item.inscription.level = item_data["main_item"]["inscription"][
                "level"
            ]
            item.main_item.inscription.weapon_instance_id = item_data["main_item"][
                "inscription"
            ]["weapon_instance_id"]

            # Set pack type and extra quality
            item.pack_type = item_data["pack_type"]
            item.extra_quality = item_data["extra_quality"]

        session.send(CmdId.ShopBuyRsp, rsp, False, packet_id)

        # Call PlayerVitality handler to send vitality data notification
        try:
            from handlers.PlayerVitality import Handler as PlayerVitalityHandler

            player_vitality_handler = PlayerVitalityHandler()
            # Create empty data for PlayerVitality
            player_vitality_handler.handle(session, b"", packet_id)
        except Exception as e:
            logger.error(f"Failed to send PlayerVitality: {e}")


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "shop_id": 500,
    "grids": {
        "id": 500,
        "grid_id": 2,
        "pool_id": 502,
        "pool_index": 1,
        "buy_times": 48,
        "update_time": 0,
    },
    "items": [
        {
            "main_item": {
                "item_id": 110,
                "item_tag": 9,
                "is_new": False,
                "temp_pack_index": 0,
                "base_item": {"item_id": 110, "num": 10},
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
