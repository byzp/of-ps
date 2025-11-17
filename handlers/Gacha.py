from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import json
import os

import proto.OverField_pb2 as Gacha_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GachaReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # Parse request
        req = Gacha_pb2.GachaReq()
        req.ParseFromString(data)

        # Load hardcoded data from JSON file
        json_file_path = os.path.join(
            os.path.dirname(__file__), "..", "tmp", "data", "GachaRsp.json"
        )
        with open(json_file_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        parsed_result = json_data.get("parsed_result", {})

        # Create response message
        rsp = Gacha_pb2.GachaRsp()

        # Set status
        rsp.status = parsed_result.get("status", 1)

        # Set items
        items_data = parsed_result.get("items", [])
        for item_data in items_data:
            item = rsp.items.add()

            # Set main_item
            main_item_data = item_data.get("main_item", {})
            if main_item_data:
                item.main_item.item_id = main_item_data.get("item_id", 0)
                item.main_item.item_tag = main_item_data.get("item_tag", 0)
                item.main_item.is_new = main_item_data.get("is_new", False)
                item.main_item.temp_pack_index = main_item_data.get(
                    "temp_pack_index", 0
                )

                # Set base_item
                base_item_data = main_item_data.get("base_item", {})
                if base_item_data:
                    item.main_item.base_item.item_id = base_item_data.get("item_id", 0)
                    item.main_item.base_item.num = base_item_data.get("num", 0)

                # Set weapon
                weapon_data = main_item_data.get("weapon", {})
                if weapon_data:
                    item.main_item.weapon.weapon_id = weapon_data.get("weapon_id", 0)
                    item.main_item.weapon.instance_id = weapon_data.get(
                        "instance_id", 0
                    )
                    item.main_item.weapon.attack = weapon_data.get("attack", 0)
                    item.main_item.weapon.damage_balance = weapon_data.get(
                        "damage_balance", 0
                    )
                    item.main_item.weapon.critical_ratio = weapon_data.get(
                        "critical_ratio", 0
                    )
                    item.main_item.weapon.wearer_id = weapon_data.get("wearer_id", 0)
                    item.main_item.weapon.level = weapon_data.get("level", 0)
                    item.main_item.weapon.strength_level = weapon_data.get(
                        "strength_level", 0
                    )
                    item.main_item.weapon.strength_exp = weapon_data.get(
                        "strength_exp", 0
                    )
                    item.main_item.weapon.star = weapon_data.get("star", 0)
                    item.main_item.weapon.inscription_1 = weapon_data.get(
                        "inscription_1", 0
                    )
                    item.main_item.weapon.durability = weapon_data.get("durability", 0)
                    item.main_item.weapon.property_index = weapon_data.get(
                        "property_index", 0
                    )
                    item.main_item.weapon.is_lock = weapon_data.get("is_lock", False)

                    # Set random_property
                    random_properties_data = weapon_data.get("random_property", [])
                    for random_property_data in random_properties_data:
                        random_property = item.main_item.weapon.random_property.add()
                        random_property.property_type = random_property_data.get(
                            "property_type", 0
                        )
                        random_property.value = random_property_data.get("value", 0)

                # Set armor
                armor_data = main_item_data.get("armor", {})
                if armor_data:
                    item.main_item.armor.armor_id = armor_data.get("armor_id", 0)
                    item.main_item.armor.instance_id = armor_data.get("instance_id", 0)
                    item.main_item.armor.main_property_type = armor_data.get(
                        "main_property_type", 0
                    )
                    item.main_item.armor.main_property_val = armor_data.get(
                        "main_property_val", 0
                    )
                    item.main_item.armor.wearer_id = armor_data.get("wearer_id", 0)
                    item.main_item.armor.level = armor_data.get("level", 0)
                    item.main_item.armor.strength_level = armor_data.get(
                        "strength_level", 0
                    )
                    item.main_item.armor.strength_exp = armor_data.get(
                        "strength_exp", 0
                    )
                    item.main_item.armor.property_index = armor_data.get(
                        "property_index", 0
                    )
                    item.main_item.armor.is_lock = armor_data.get("is_lock", False)

                    # Set random_property
                    random_properties_data = armor_data.get("random_property", [])
                    for random_property_data in random_properties_data:
                        random_property = item.main_item.armor.random_property.add()
                        random_property.property_type = random_property_data.get(
                            "property_type", 0
                        )
                        random_property.value = random_property_data.get("value", 0)

                # Set poster
                poster_data = main_item_data.get("poster", {})
                if poster_data:
                    item.main_item.poster.poster_id = poster_data.get("poster_id", 0)
                    item.main_item.poster.instance_id = poster_data.get(
                        "instance_id", 0
                    )
                    item.main_item.poster.wearer_id = poster_data.get("wearer_id", 0)
                    item.main_item.poster.star = poster_data.get("star", 0)

                # Set character
                character_data = main_item_data.get("character", {})
                if character_data:
                    item.main_item.character.character_id = character_data.get(
                        "character_id", 0
                    )
                    item.main_item.character.level = character_data.get("level", 0)
                    item.main_item.character.max_level = character_data.get(
                        "max_level", 0
                    )
                    item.main_item.character.exp = character_data.get("exp", 0)
                    item.main_item.character.star = character_data.get("star", 0)
                    item.main_item.character.in_use_equipment_preset_index = (
                        character_data.get("in_use_equipment_preset_index", 0)
                    )
                    item.main_item.character.in_use_outfit_preset_index = (
                        character_data.get("in_use_outfit_preset_index", 0)
                    )
                    item.main_item.character.gather_weapon = character_data.get(
                        "gather_weapon", 0
                    )
                    item.main_item.character.is_unlock_payment = character_data.get(
                        "is_unlock_payment", False
                    )

                    # Set character_appearance
                    character_appearance_data = character_data.get(
                        "character_appearance", {}
                    )
                    if character_appearance_data:
                        item.main_item.character.character_appearance.badge = (
                            character_appearance_data.get("badge", 0)
                        )
                        item.main_item.character.character_appearance.umbrella_id = (
                            character_appearance_data.get("umbrella_id", 0)
                        )
                        item.main_item.character.character_appearance.insect_net_instance_id = character_appearance_data.get(
                            "insect_net_instance_id", 0
                        )
                        item.main_item.character.character_appearance.logging_axe_instance_id = character_appearance_data.get(
                            "logging_axe_instance_id", 0
                        )
                        item.main_item.character.character_appearance.water_bottle_instance_id = character_appearance_data.get(
                            "water_bottle_instance_id", 0
                        )
                        item.main_item.character.character_appearance.mining_hammer_instance_id = character_appearance_data.get(
                            "mining_hammer_instance_id", 0
                        )
                        item.main_item.character.character_appearance.collection_gloves_instance_id = character_appearance_data.get(
                            "collection_gloves_instance_id", 0
                        )
                        item.main_item.character.character_appearance.fishing_rod_instance_id = character_appearance_data.get(
                            "fishing_rod_instance_id", 0
                        )

                    # Set equipment_presets
                    equipment_presets_data = character_data.get("equipment_presets", [])
                    for equipment_preset_data in equipment_presets_data:
                        equipment_preset = (
                            item.main_item.character.equipment_presets.add()
                        )
                        equipment_preset.preset_index = equipment_preset_data.get(
                            "preset_index", 0
                        )
                        equipment_preset.weapon = equipment_preset_data.get("weapon", 0)

                        # Set armors
                        armors_data = equipment_preset_data.get("armors", [])
                        for armor_data in armors_data:
                            armor = equipment_preset.armors.add()
                            armor.equip_type = armor_data.get("equip_type", 0)
                            armor.armor_id = armor_data.get("armor_id", 0)

                        # Set posters
                        posters_data = equipment_preset_data.get("posters", [])
                        for poster_data in posters_data:
                            poster = equipment_preset.posters.add()
                            poster.poster_index = poster_data.get("poster_index", 0)
                            poster.poster_id = poster_data.get("poster_id", 0)

                    # Set outfit_presets
                    outfit_presets_data = character_data.get("outfit_presets", [])
                    for outfit_preset_data in outfit_presets_data:
                        outfit_preset = item.main_item.character.outfit_presets.add()
                        outfit_preset.preset_index = outfit_preset_data.get(
                            "preset_index", 0
                        )
                        outfit_preset.hat = outfit_preset_data.get("hat", 0)
                        outfit_preset.hair = outfit_preset_data.get("hair", 0)
                        outfit_preset.clothes = outfit_preset_data.get("clothes", 0)
                        outfit_preset.ornament = outfit_preset_data.get("ornament", 0)
                        outfit_preset.hat_dye_scheme_index = outfit_preset_data.get(
                            "hat_dye_scheme_index", 0
                        )
                        outfit_preset.hair_dye_scheme_index = outfit_preset_data.get(
                            "hair_dye_scheme_index", 0
                        )
                        outfit_preset.clothes_dye_scheme_index = outfit_preset_data.get(
                            "clothes_dye_scheme_index", 0
                        )
                        outfit_preset.ornament_dye_scheme_index = (
                            outfit_preset_data.get("ornament_dye_scheme_index", 0)
                        )

                    # Set character_skill_list
                    character_skill_list_data = character_data.get(
                        "character_skill_list", []
                    )
                    for character_skill_data in character_skill_list_data:
                        character_skill = (
                            item.main_item.character.character_skill_list.add()
                        )
                        character_skill.skill_id = character_skill_data.get(
                            "skill_id", 0
                        )
                        character_skill.skill_level = character_skill_data.get(
                            "skill_level", 0
                        )

                    # Set rewarded_achievement_id_lst
                    rewarded_achievement_id_lst_data = character_data.get(
                        "rewarded_achievement_id_lst", []
                    )
                    for achievement_id in rewarded_achievement_id_lst_data:
                        item.main_item.character.rewarded_achievement_id_lst.append(
                            achievement_id
                        )

                    # Set reward_index_lst
                    reward_index_lst_data = character_data.get("reward_index_lst", [])
                    for reward_index in reward_index_lst_data:
                        item.main_item.character.reward_index_lst.append(reward_index)

                # Set outfit
                outfit_data = main_item_data.get("outfit", {})
                if outfit_data:
                    item.main_item.outfit.outfit_id = outfit_data.get("outfit_id", 0)

                    # Set dye_schemes
                    dye_schemes_data = outfit_data.get("dye_schemes", [])
                    for dye_scheme_data in dye_schemes_data:
                        dye_scheme = item.main_item.outfit.dye_schemes.add()
                        dye_scheme.outfit_id = dye_scheme_data.get("outfit_id", 0)
                        dye_scheme.scheme_index = dye_scheme_data.get("scheme_index", 0)
                        dye_scheme.pos = dye_scheme_data.get("pos", 0)
                        dye_scheme.dye_item_id = dye_scheme_data.get("dye_item_id", 0)

                        # Set color
                        color_data = dye_scheme_data.get("color", {})
                        if color_data:
                            dye_scheme.color.pos = color_data.get("pos", 0)
                            dye_scheme.color.red = color_data.get("red", 0)
                            dye_scheme.color.green = color_data.get("green", 0)
                            dye_scheme.color.blue = color_data.get("blue", 0)

                # Set inscription
                inscription_data = main_item_data.get("inscription", {})
                if inscription_data:
                    item.main_item.inscription.inscription_id = inscription_data.get(
                        "inscription_id", 0
                    )
                    item.main_item.inscription.level = inscription_data.get("level", 0)
                    item.main_item.inscription.weapon_instance_id = (
                        inscription_data.get("weapon_instance_id", 0)
                    )

            # Set transformed_item
            transformed_items_data = item_data.get("transformed_item", [])
            for transformed_item_data in transformed_items_data:
                transformed_item = item.transformed_item.add()
                transformed_item.item_id = transformed_item_data.get("item_id", 0)
                transformed_item.item_tag = transformed_item_data.get("item_tag", 0)
                transformed_item.is_new = transformed_item_data.get("is_new", False)
                transformed_item.temp_pack_index = transformed_item_data.get(
                    "temp_pack_index", 0
                )

                # Set base_item
                base_item_data = transformed_item_data.get("base_item", {})
                if base_item_data:
                    transformed_item.base_item.item_id = base_item_data.get(
                        "item_id", 0
                    )
                    transformed_item.base_item.num = base_item_data.get("num", 0)

                # Set weapon
                weapon_data = transformed_item_data.get("weapon", {})
                if weapon_data:
                    transformed_item.weapon.weapon_id = weapon_data.get("weapon_id", 0)
                    transformed_item.weapon.instance_id = weapon_data.get(
                        "instance_id", 0
                    )
                    transformed_item.weapon.attack = weapon_data.get("attack", 0)
                    transformed_item.weapon.damage_balance = weapon_data.get(
                        "damage_balance", 0
                    )
                    transformed_item.weapon.critical_ratio = weapon_data.get(
                        "critical_ratio", 0
                    )
                    transformed_item.weapon.wearer_id = weapon_data.get("wearer_id", 0)
                    transformed_item.weapon.level = weapon_data.get("level", 0)
                    transformed_item.weapon.strength_level = weapon_data.get(
                        "strength_level", 0
                    )
                    transformed_item.weapon.strength_exp = weapon_data.get(
                        "strength_exp", 0
                    )
                    transformed_item.weapon.star = weapon_data.get("star", 0)
                    transformed_item.weapon.inscription_1 = weapon_data.get(
                        "inscription_1", 0
                    )
                    transformed_item.weapon.durability = weapon_data.get(
                        "durability", 0
                    )
                    transformed_item.weapon.property_index = weapon_data.get(
                        "property_index", 0
                    )
                    transformed_item.weapon.is_lock = weapon_data.get("is_lock", False)

                    # Set random_property
                    random_properties_data = weapon_data.get("random_property", [])
                    for random_property_data in random_properties_data:
                        random_property = transformed_item.weapon.random_property.add()
                        random_property.property_type = random_property_data.get(
                            "property_type", 0
                        )
                        random_property.value = random_property_data.get("value", 0)

                # Set armor
                armor_data = transformed_item_data.get("armor", {})
                if armor_data:
                    transformed_item.armor.armor_id = armor_data.get("armor_id", 0)
                    transformed_item.armor.instance_id = armor_data.get(
                        "instance_id", 0
                    )
                    transformed_item.armor.main_property_type = armor_data.get(
                        "main_property_type", 0
                    )
                    transformed_item.armor.main_property_val = armor_data.get(
                        "main_property_val", 0
                    )
                    transformed_item.armor.wearer_id = armor_data.get("wearer_id", 0)
                    transformed_item.armor.level = armor_data.get("level", 0)
                    transformed_item.armor.strength_level = armor_data.get(
                        "strength_level", 0
                    )
                    transformed_item.armor.strength_exp = armor_data.get(
                        "strength_exp", 0
                    )
                    transformed_item.armor.property_index = armor_data.get(
                        "property_index", 0
                    )
                    transformed_item.armor.is_lock = armor_data.get("is_lock", False)

                    # Set random_property
                    random_properties_data = armor_data.get("random_property", [])
                    for random_property_data in random_properties_data:
                        random_property = transformed_item.armor.random_property.add()
                        random_property.property_type = random_property_data.get(
                            "property_type", 0
                        )
                        random_property.value = random_property_data.get("value", 0)

                # Set poster
                poster_data = transformed_item_data.get("poster", {})
                if poster_data:
                    transformed_item.poster.poster_id = poster_data.get("poster_id", 0)
                    transformed_item.poster.instance_id = poster_data.get(
                        "instance_id", 0
                    )
                    transformed_item.poster.wearer_id = poster_data.get("wearer_id", 0)
                    transformed_item.poster.star = poster_data.get("star", 0)

                # Set character
                character_data = transformed_item_data.get("character", {})
                if character_data:
                    transformed_item.character.character_id = character_data.get(
                        "character_id", 0
                    )
                    transformed_item.character.level = character_data.get("level", 0)
                    transformed_item.character.max_level = character_data.get(
                        "max_level", 0
                    )
                    transformed_item.character.exp = character_data.get("exp", 0)
                    transformed_item.character.star = character_data.get("star", 0)
                    transformed_item.character.in_use_equipment_preset_index = (
                        character_data.get("in_use_equipment_preset_index", 0)
                    )
                    transformed_item.character.in_use_outfit_preset_index = (
                        character_data.get("in_use_outfit_preset_index", 0)
                    )
                    transformed_item.character.gather_weapon = character_data.get(
                        "gather_weapon", 0
                    )
                    transformed_item.character.is_unlock_payment = character_data.get(
                        "is_unlock_payment", False
                    )

                    # Set character_appearance
                    character_appearance_data = character_data.get(
                        "character_appearance", {}
                    )
                    if character_appearance_data:
                        transformed_item.character.character_appearance.badge = (
                            character_appearance_data.get("badge", 0)
                        )
                        transformed_item.character.character_appearance.umbrella_id = (
                            character_appearance_data.get("umbrella_id", 0)
                        )
                        transformed_item.character.character_appearance.insect_net_instance_id = character_appearance_data.get(
                            "insect_net_instance_id", 0
                        )
                        transformed_item.character.character_appearance.logging_axe_instance_id = character_appearance_data.get(
                            "logging_axe_instance_id", 0
                        )
                        transformed_item.character.character_appearance.water_bottle_instance_id = character_appearance_data.get(
                            "water_bottle_instance_id", 0
                        )
                        transformed_item.character.character_appearance.mining_hammer_instance_id = character_appearance_data.get(
                            "mining_hammer_instance_id", 0
                        )
                        transformed_item.character.character_appearance.collection_gloves_instance_id = character_appearance_data.get(
                            "collection_gloves_instance_id", 0
                        )
                        transformed_item.character.character_appearance.fishing_rod_instance_id = character_appearance_data.get(
                            "fishing_rod_instance_id", 0
                        )

                    # Set equipment_presets
                    equipment_presets_data = character_data.get("equipment_presets", [])
                    for equipment_preset_data in equipment_presets_data:
                        equipment_preset = (
                            transformed_item.character.equipment_presets.add()
                        )
                        equipment_preset.preset_index = equipment_preset_data.get(
                            "preset_index", 0
                        )
                        equipment_preset.weapon = equipment_preset_data.get("weapon", 0)

                        # Set armors
                        armors_data = equipment_preset_data.get("armors", [])
                        for armor_data in armors_data:
                            armor = equipment_preset.armors.add()
                            armor.equip_type = armor_data.get("equip_type", 0)
                            armor.armor_id = armor_data.get("armor_id", 0)

                        # Set posters
                        posters_data = equipment_preset_data.get("posters", [])
                        for poster_data in posters_data:
                            poster = equipment_preset.posters.add()
                            poster.poster_index = poster_data.get("poster_index", 0)
                            poster.poster_id = poster_data.get("poster_id", 0)

                    # Set outfit_presets
                    outfit_presets_data = character_data.get("outfit_presets", [])
                    for outfit_preset_data in outfit_presets_data:
                        outfit_preset = transformed_item.character.outfit_presets.add()
                        outfit_preset.preset_index = outfit_preset_data.get(
                            "preset_index", 0
                        )
                        outfit_preset.hat = outfit_preset_data.get("hat", 0)
                        outfit_preset.hair = outfit_preset_data.get("hair", 0)
                        outfit_preset.clothes = outfit_preset_data.get("clothes", 0)
                        outfit_preset.ornament = outfit_preset_data.get("ornament", 0)
                        outfit_preset.hat_dye_scheme_index = outfit_preset_data.get(
                            "hat_dye_scheme_index", 0
                        )
                        outfit_preset.hair_dye_scheme_index = outfit_preset_data.get(
                            "hair_dye_scheme_index", 0
                        )
                        outfit_preset.clothes_dye_scheme_index = outfit_preset_data.get(
                            "clothes_dye_scheme_index", 0
                        )
                        outfit_preset.ornament_dye_scheme_index = (
                            outfit_preset_data.get("ornament_dye_scheme_index", 0)
                        )

                    # Set character_skill_list
                    character_skill_list_data = character_data.get(
                        "character_skill_list", []
                    )
                    for character_skill_data in character_skill_list_data:
                        character_skill = (
                            transformed_item.character.character_skill_list.add()
                        )
                        character_skill.skill_id = character_skill_data.get(
                            "skill_id", 0
                        )
                        character_skill.skill_level = character_skill_data.get(
                            "skill_level", 0
                        )

                    # Set rewarded_achievement_id_lst
                    rewarded_achievement_id_lst_data = character_data.get(
                        "rewarded_achievement_id_lst", []
                    )
                    for achievement_id in rewarded_achievement_id_lst_data:
                        transformed_item.character.rewarded_achievement_id_lst.append(
                            achievement_id
                        )

                    # Set reward_index_lst
                    reward_index_lst_data = character_data.get("reward_index_lst", [])
                    for reward_index in reward_index_lst_data:
                        transformed_item.character.reward_index_lst.append(reward_index)

                # Set outfit
                outfit_data = transformed_item_data.get("outfit", {})
                if outfit_data:
                    transformed_item.outfit.outfit_id = outfit_data.get("outfit_id", 0)

                    # Set dye_schemes
                    dye_schemes_data = outfit_data.get("dye_schemes", [])
                    for dye_scheme_data in dye_schemes_data:
                        dye_scheme = transformed_item.outfit.dye_schemes.add()
                        dye_scheme.outfit_id = dye_scheme_data.get("outfit_id", 0)
                        dye_scheme.scheme_index = dye_scheme_data.get("scheme_index", 0)
                        dye_scheme.pos = dye_scheme_data.get("pos", 0)
                        dye_scheme.dye_item_id = dye_scheme_data.get("dye_item_id", 0)

                        # Set color
                        color_data = dye_scheme_data.get("color", {})
                        if color_data:
                            dye_scheme.color.pos = color_data.get("pos", 0)
                            dye_scheme.color.red = color_data.get("red", 0)
                            dye_scheme.color.green = color_data.get("green", 0)
                            dye_scheme.color.blue = color_data.get("blue", 0)

                # Set inscription
                inscription_data = transformed_item_data.get("inscription", {})
                if inscription_data:
                    transformed_item.inscription.inscription_id = inscription_data.get(
                        "inscription_id", 0
                    )
                    transformed_item.inscription.level = inscription_data.get(
                        "level", 0
                    )
                    transformed_item.inscription.weapon_instance_id = (
                        inscription_data.get("weapon_instance_id", 0)
                    )

            # Set extras
            extras_data = item_data.get("extras", [])
            for extra_data in extras_data:
                extra = item.extras.add()
                extra.item_id = extra_data.get("item_id", 0)
                extra.item_tag = extra_data.get("item_tag", 0)
                extra.is_new = extra_data.get("is_new", False)
                extra.temp_pack_index = extra_data.get("temp_pack_index", 0)

                # Set base_item
                base_item_data = extra_data.get("base_item", {})
                if base_item_data:
                    extra.base_item.item_id = base_item_data.get("item_id", 0)
                    extra.base_item.num = base_item_data.get("num", 0)

                # Set weapon
                weapon_data = extra_data.get("weapon", {})
                if weapon_data:
                    extra.weapon.weapon_id = weapon_data.get("weapon_id", 0)
                    extra.weapon.instance_id = weapon_data.get("instance_id", 0)
                    extra.weapon.attack = weapon_data.get("attack", 0)
                    extra.weapon.damage_balance = weapon_data.get("damage_balance", 0)
                    extra.weapon.critical_ratio = weapon_data.get("critical_ratio", 0)
                    extra.weapon.wearer_id = weapon_data.get("wearer_id", 0)
                    extra.weapon.level = weapon_data.get("level", 0)
                    extra.weapon.strength_level = weapon_data.get("strength_level", 0)
                    extra.weapon.strength_exp = weapon_data.get("strength_exp", 0)
                    extra.weapon.star = weapon_data.get("star", 0)
                    extra.weapon.inscription_1 = weapon_data.get("inscription_1", 0)
                    extra.weapon.durability = weapon_data.get("durability", 0)
                    extra.weapon.property_index = weapon_data.get("property_index", 0)
                    extra.weapon.is_lock = weapon_data.get("is_lock", False)

                    # Set random_property
                    random_properties_data = weapon_data.get("random_property", [])
                    for random_property_data in random_properties_data:
                        random_property = extra.weapon.random_property.add()
                        random_property.property_type = random_property_data.get(
                            "property_type", 0
                        )
                        random_property.value = random_property_data.get("value", 0)

                # Set armor
                armor_data = extra_data.get("armor", {})
                if armor_data:
                    extra.armor.armor_id = armor_data.get("armor_id", 0)
                    extra.armor.instance_id = armor_data.get("instance_id", 0)
                    extra.armor.main_property_type = armor_data.get(
                        "main_property_type", 0
                    )
                    extra.armor.main_property_val = armor_data.get(
                        "main_property_val", 0
                    )
                    extra.armor.wearer_id = armor_data.get("wearer_id", 0)
                    extra.armor.level = armor_data.get("level", 0)
                    extra.armor.strength_level = armor_data.get("strength_level", 0)
                    extra.armor.strength_exp = armor_data.get("strength_exp", 0)
                    extra.armor.property_index = armor_data.get("property_index", 0)
                    extra.armor.is_lock = armor_data.get("is_lock", False)

                    # Set random_property
                    random_properties_data = armor_data.get("random_property", [])
                    for random_property_data in random_properties_data:
                        random_property = extra.armor.random_property.add()
                        random_property.property_type = random_property_data.get(
                            "property_type", 0
                        )
                        random_property.value = random_property_data.get("value", 0)

                # Set poster
                poster_data = extra_data.get("poster", {})
                if poster_data:
                    extra.poster.poster_id = poster_data.get("poster_id", 0)
                    extra.poster.instance_id = poster_data.get("instance_id", 0)
                    extra.poster.wearer_id = poster_data.get("wearer_id", 0)
                    extra.poster.star = poster_data.get("star", 0)

                # Set character
                character_data = extra_data.get("character", {})
                if character_data:
                    extra.character.character_id = character_data.get("character_id", 0)
                    extra.character.level = character_data.get("level", 0)
                    extra.character.max_level = character_data.get("max_level", 0)
                    extra.character.exp = character_data.get("exp", 0)
                    extra.character.star = character_data.get("star", 0)
                    extra.character.in_use_equipment_preset_index = character_data.get(
                        "in_use_equipment_preset_index", 0
                    )
                    extra.character.in_use_outfit_preset_index = character_data.get(
                        "in_use_outfit_preset_index", 0
                    )
                    extra.character.gather_weapon = character_data.get(
                        "gather_weapon", 0
                    )
                    extra.character.is_unlock_payment = character_data.get(
                        "is_unlock_payment", False
                    )

                    # Set character_appearance
                    character_appearance_data = character_data.get(
                        "character_appearance", {}
                    )
                    if character_appearance_data:
                        extra.character.character_appearance.badge = (
                            character_appearance_data.get("badge", 0)
                        )
                        extra.character.character_appearance.umbrella_id = (
                            character_appearance_data.get("umbrella_id", 0)
                        )
                        extra.character.character_appearance.insect_net_instance_id = (
                            character_appearance_data.get("insect_net_instance_id", 0)
                        )
                        extra.character.character_appearance.logging_axe_instance_id = (
                            character_appearance_data.get("logging_axe_instance_id", 0)
                        )
                        extra.character.character_appearance.water_bottle_instance_id = character_appearance_data.get(
                            "water_bottle_instance_id", 0
                        )
                        extra.character.character_appearance.mining_hammer_instance_id = character_appearance_data.get(
                            "mining_hammer_instance_id", 0
                        )
                        extra.character.character_appearance.collection_gloves_instance_id = character_appearance_data.get(
                            "collection_gloves_instance_id", 0
                        )
                        extra.character.character_appearance.fishing_rod_instance_id = (
                            character_appearance_data.get("fishing_rod_instance_id", 0)
                        )

                    # Set equipment_presets
                    equipment_presets_data = character_data.get("equipment_presets", [])
                    for equipment_preset_data in equipment_presets_data:
                        equipment_preset = extra.character.equipment_presets.add()
                        equipment_preset.preset_index = equipment_preset_data.get(
                            "preset_index", 0
                        )
                        equipment_preset.weapon = equipment_preset_data.get("weapon", 0)

                        # Set armors
                        armors_data = equipment_preset_data.get("armors", [])
                        for armor_data in armors_data:
                            armor = equipment_preset.armors.add()
                            armor.equip_type = armor_data.get("equip_type", 0)
                            armor.armor_id = armor_data.get("armor_id", 0)

                        # Set posters
                        posters_data = equipment_preset_data.get("posters", [])
                        for poster_data in posters_data:
                            poster = equipment_preset.posters.add()
                            poster.poster_index = poster_data.get("poster_index", 0)
                            poster.poster_id = poster_data.get("poster_id", 0)

                    # Set outfit_presets
                    outfit_presets_data = character_data.get("outfit_presets", [])
                    for outfit_preset_data in outfit_presets_data:
                        outfit_preset = extra.character.outfit_presets.add()
                        outfit_preset.preset_index = outfit_preset_data.get(
                            "preset_index", 0
                        )
                        outfit_preset.hat = outfit_preset_data.get("hat", 0)
                        outfit_preset.hair = outfit_preset_data.get("hair", 0)
                        outfit_preset.clothes = outfit_preset_data.get("clothes", 0)
                        outfit_preset.ornament = outfit_preset_data.get("ornament", 0)
                        outfit_preset.hat_dye_scheme_index = outfit_preset_data.get(
                            "hat_dye_scheme_index", 0
                        )
                        outfit_preset.hair_dye_scheme_index = outfit_preset_data.get(
                            "hair_dye_scheme_index", 0
                        )
                        outfit_preset.clothes_dye_scheme_index = outfit_preset_data.get(
                            "clothes_dye_scheme_index", 0
                        )
                        outfit_preset.ornament_dye_scheme_index = (
                            outfit_preset_data.get("ornament_dye_scheme_index", 0)
                        )

                    # Set character_skill_list
                    character_skill_list_data = character_data.get(
                        "character_skill_list", []
                    )
                    for character_skill_data in character_skill_list_data:
                        character_skill = extra.character.character_skill_list.add()
                        character_skill.skill_id = character_skill_data.get(
                            "skill_id", 0
                        )
                        character_skill.skill_level = character_skill_data.get(
                            "skill_level", 0
                        )

                    # Set rewarded_achievement_id_lst
                    rewarded_achievement_id_lst_data = character_data.get(
                        "rewarded_achievement_id_lst", []
                    )
                    for achievement_id in rewarded_achievement_id_lst_data:
                        extra.character.rewarded_achievement_id_lst.append(
                            achievement_id
                        )

                    # Set reward_index_lst
                    reward_index_lst_data = character_data.get("reward_index_lst", [])
                    for reward_index in reward_index_lst_data:
                        extra.character.reward_index_lst.append(reward_index)

                # Set outfit
                outfit_data = extra_data.get("outfit", {})
                if outfit_data:
                    extra.outfit.outfit_id = outfit_data.get("outfit_id", 0)

                    # Set dye_schemes
                    dye_schemes_data = outfit_data.get("dye_schemes", [])
                    for dye_scheme_data in dye_schemes_data:
                        dye_scheme = extra.outfit.dye_schemes.add()
                        dye_scheme.outfit_id = dye_scheme_data.get("outfit_id", 0)
                        dye_scheme.scheme_index = dye_scheme_data.get("scheme_index", 0)
                        dye_scheme.pos = dye_scheme_data.get("pos", 0)
                        dye_scheme.dye_item_id = dye_scheme_data.get("dye_item_id", 0)

                        # Set color
                        color_data = dye_scheme_data.get("color", {})
                        if color_data:
                            dye_scheme.color.pos = color_data.get("pos", 0)
                            dye_scheme.color.red = color_data.get("red", 0)
                            dye_scheme.color.green = color_data.get("green", 0)
                            dye_scheme.color.blue = color_data.get("blue", 0)

                # Set inscription
                inscription_data = extra_data.get("inscription", {})
                if inscription_data:
                    extra.inscription.inscription_id = inscription_data.get(
                        "inscription_id", 0
                    )
                    extra.inscription.level = inscription_data.get("level", 0)
                    extra.inscription.weapon_instance_id = inscription_data.get(
                        "weapon_instance_id", 0
                    )

            # Set pack_type and extra_quality
            item.pack_type = item_data.get("pack_type", 0)
            item.extra_quality = item_data.get("extra_quality", 0)

        # Set info
        info_data = parsed_result.get("info", {})
        if info_data:
            rsp.info.gacha_id = info_data.get("gacha_id", 0)
            rsp.info.gacha_times = info_data.get("gacha_times", 0)
            rsp.info.has_full_pick = info_data.get("has_full_pick", False)
            rsp.info.is_free = info_data.get("is_free", False)
            rsp.info.optional_up_item = info_data.get("optional_up_item", 0)
            rsp.info.optional_value = info_data.get("optional_value", 0)
            rsp.info.guarantee = info_data.get("guarantee", 0)

        # Send response
        session.send(CmdId.GachaRsp, rsp, False, packet_id)
