from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import json
import os

import proto.OverField_pb2 as SceneDataNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.SceneDataNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # Load hardcoded data from JSON file
        json_file_path = os.path.join(
            os.path.dirname(__file__), "..", "tmp", "data", "SceneDataNotice.json"
        )
        with open(json_file_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        parsed_result = json_data.get("parsed_result", {})

        # Create response message
        rsp = SceneDataNotice_pb2.SceneDataNotice()

        # Set status
        rsp.status = parsed_result.get("status", 1)

        # Set data
        data_obj = parsed_result.get("data", {})
        if data_obj:
            # Set basic fields
            rsp.data.scene_id = data_obj.get("scene_id", 0)

            # Set gather_limits
            for gather_limit_data in data_obj.get("gather_limits", []):
                gather_limit = rsp.data.gather_limits.add()
                gather_limit.gather_type = gather_limit_data.get("gather_type", 0)
                gather_limit.gather_num = gather_limit_data.get("gather_num", 0)
                gather_limit.gather_limit_num = gather_limit_data.get(
                    "gather_limit_num", 0
                )
                gather_limit.lucky_gather_limit_num = gather_limit_data.get(
                    "lucky_gather_limit_num", 0
                )

            # Set drop_items (empty in this case)
            # No drop items in the sample data

            # Set areas
            for area_data in data_obj.get("areas", []):
                area = rsp.data.areas.add()
                area.area_id = area_data.get("area_id", 0)
                area.area_state = area_data.get("area_state", 0)
                area.level = area_data.get("level", 0)
                # items are empty in this case

            # Set collections
            for collection_data in data_obj.get("collections", []):
                collection = rsp.data.collections.add()
                collection.type = collection_data.get("type", 0)
                collection.level = collection_data.get("level", 0)
                collection.exp = collection_data.get("exp", 0)
                # item_map is empty in this case

            # Set challenges
            for challenge_data in data_obj.get("challenges", []):
                challenge = rsp.data.challenges.add()
                challenge.challenge_id = challenge_data.get("challenge_id", 0)
                challenge.use_time = challenge_data.get("use_time", 0)
                challenge.state = challenge_data.get("state", 0)
                challenge.star = challenge_data.get("star", 0)

            # Set treasure_boxes
            for treasure_box_data in data_obj.get("treasure_boxes", []):
                treasure_box = rsp.data.treasure_boxes.add()
                treasure_box.index = treasure_box_data.get("index", 0)
                treasure_box.box_id = treasure_box_data.get("box_id", 0)
                treasure_box.type = treasure_box_data.get("type", 0)
                treasure_box.state = treasure_box_data.get("state", 0)
                treasure_box.next_refresh_time = treasure_box_data.get(
                    "next_refresh_time", 0
                )
                # rewards are empty in this case

            # Set riddles
            for riddle_data in data_obj.get("riddles", []):
                riddle = rsp.data.riddles.add()
                riddle.riddle_id = riddle_data.get("riddle_id", 0)
                riddle.is_win = riddle_data.get("is_win", False)
                riddle.state = riddle_data.get("state", 0)

            # Set monsters
            for monster_data in data_obj.get("monsters", []):
                monster = rsp.data.monsters.add()
                monster.monster_id = monster_data.get("monster_id", 0)
                monster.monster_index = monster_data.get("monster_index", 0)

            # Set battle_encounters
            for battle_encounter_data in data_obj.get("battle_encounters", []):
                battle_encounter = rsp.data.battle_encounters.add()
                battle_encounter.battle_id = battle_encounter_data.get("battle_id", 0)
                battle_encounter.state = battle_encounter_data.get("state", 0)
                battle_encounter.box_id = battle_encounter_data.get("box_id", 0)

            # Set flag_battles
            for flag_battle_data in data_obj.get("flag_battles", []):
                flag_battle = rsp.data.flag_battles.add()
                flag_battle.battle_id = flag_battle_data.get("battle_id", 0)
                flag_battle.state = flag_battle_data.get("state", 0)
                flag_battle.type = flag_battle_data.get("type", 0)
                flag_battle.finish_times = flag_battle_data.get("finish_times", 0)
                flag_battle.voice_id = flag_battle_data.get("voice_id", 0)

            # Set bon_fires
            for bonfire_data in data_obj.get("bon_fires", []):
                bonfire = rsp.data.bon_fires.add()
                bonfire.id = bonfire_data.get("id", 0)

                # Set position
                pos_data = bonfire_data.get("position", {})
                bonfire.position.x = pos_data.get("x", 0)
                bonfire.position.y = pos_data.get("y", 0)
                bonfire.position.z = pos_data.get("z", 0)
                bonfire.position.decimal_places = pos_data.get("decimal_places", 0)

                # Set rotation
                rot_data = bonfire_data.get("rotation", {})
                bonfire.rotation.x = rot_data.get("x", 0)
                bonfire.rotation.y = rot_data.get("y", 0)
                bonfire.rotation.z = rot_data.get("z", 0)
                bonfire.rotation.decimal_places = rot_data.get("decimal_places", 0)

                bonfire.player_id = bonfire_data.get("player_id", 0)

            # Set garden_data
            garden_data = data_obj.get("garden_data", {})
            if garden_data:
                # garden_furniture_info_map is empty in this case
                rsp.data.garden_data.likes_num = garden_data.get("likes_num", 0)
                rsp.data.garden_data.access_player_num = garden_data.get(
                    "access_player_num", 0
                )
                rsp.data.garden_data.left_like_num = garden_data.get("left_like_num", 0)
                rsp.data.garden_data.garden_name = garden_data.get("garden_name", "")
                # furniture_player_map is empty in this case
                # other_player_furniture_info_map is empty in this case
                rsp.data.garden_data.furniture_current_point_num = garden_data.get(
                    "furniture_current_point_num", 0
                )
                # player_handing_furniture_info_map is empty in this case

            # Set players
            for player_data in data_obj.get("players", []):
                player = rsp.data.players.add()
                player.player_id = player_data.get("player_id", 0)
                player.player_name = player_data.get("player_name", "")

                # Set team
                team_data = player_data.get("team", {})
                if team_data:
                    # Set char_1
                    char_1_data = team_data.get("char_1", {})
                    if char_1_data:
                        player.team.char_1.char_id = char_1_data.get("char_id", 0)

                        # Set outfit_preset
                        outfit_preset_data = char_1_data.get("outfit_preset", {})
                        if outfit_preset_data:
                            player.team.char_1.outfit_preset.hat = (
                                outfit_preset_data.get("hat", 0)
                            )
                            player.team.char_1.outfit_preset.hair = (
                                outfit_preset_data.get("hair", 0)
                            )
                            player.team.char_1.outfit_preset.clothes = (
                                outfit_preset_data.get("clothes", 0)
                            )
                            player.team.char_1.outfit_preset.ornament = (
                                outfit_preset_data.get("ornament", 0)
                            )

                            # hat_dye_scheme
                            hat_dye_scheme_data = outfit_preset_data.get(
                                "hat_dye_scheme", {}
                            )
                            if hat_dye_scheme_data:
                                player.team.char_1.outfit_preset.hat_dye_scheme.scheme_index = hat_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_1.outfit_preset.hat_dye_scheme.is_un_lock = hat_dye_scheme_data.get(
                                    "is_un_lock", False
                                )
                                # colors are empty in this case

                            # hair_dye_scheme
                            hair_dye_scheme_data = outfit_preset_data.get(
                                "hair_dye_scheme", {}
                            )
                            if hair_dye_scheme_data:
                                player.team.char_1.outfit_preset.hair_dye_scheme.scheme_index = hair_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_1.outfit_preset.hair_dye_scheme.is_un_lock = hair_dye_scheme_data.get(
                                    "is_un_lock", False
                                )
                                # colors are empty in this case

                            # cloth_dye_scheme
                            cloth_dye_scheme_data = outfit_preset_data.get(
                                "cloth_dye_scheme", {}
                            )
                            if cloth_dye_scheme_data:
                                player.team.char_1.outfit_preset.cloth_dye_scheme.scheme_index = cloth_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_1.outfit_preset.cloth_dye_scheme.is_un_lock = cloth_dye_scheme_data.get(
                                    "is_un_lock", False
                                )
                                # colors are empty in this case

                            # orn_dye_scheme
                            orn_dye_scheme_data = outfit_preset_data.get(
                                "orn_dye_scheme", {}
                            )
                            if orn_dye_scheme_data:
                                player.team.char_1.outfit_preset.orn_dye_scheme.scheme_index = orn_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_1.outfit_preset.orn_dye_scheme.is_un_lock = orn_dye_scheme_data.get(
                                    "is_un_lock", False
                                )
                                # colors are empty in this case

                            # hide_info
                            hide_info_data = outfit_preset_data.get("hide_info", {})
                            if hide_info_data:
                                player.team.char_1.outfit_preset.hide_info.hide_orn = (
                                    hide_info_data.get("hide_orn", False)
                                )
                                player.team.char_1.outfit_preset.hide_info.hide_braid = hide_info_data.get(
                                    "hide_braid", False
                                )

                            player.team.char_1.outfit_preset.pend_top = (
                                outfit_preset_data.get("pend_top", 0)
                            )
                            player.team.char_1.outfit_preset.pend_chest = (
                                outfit_preset_data.get("pend_chest", 0)
                            )
                            player.team.char_1.outfit_preset.pend_pelvis = (
                                outfit_preset_data.get("pend_pelvis", 0)
                            )
                            player.team.char_1.outfit_preset.pend_up_face = (
                                outfit_preset_data.get("pend_up_face", 0)
                            )
                            player.team.char_1.outfit_preset.pend_down_face = (
                                outfit_preset_data.get("pend_down_face", 0)
                            )
                            player.team.char_1.outfit_preset.pend_left_hand = (
                                outfit_preset_data.get("pend_left_hand", 0)
                            )
                            player.team.char_1.outfit_preset.pend_right_hand = (
                                outfit_preset_data.get("pend_right_hand", 0)
                            )
                            player.team.char_1.outfit_preset.pend_left_foot = (
                                outfit_preset_data.get("pend_left_foot", 0)
                            )
                            player.team.char_1.outfit_preset.pend_right_foot = (
                                outfit_preset_data.get("pend_right_foot", 0)
                            )

                            # pend_chest_dye_scheme
                            pend_chest_dye_scheme_data = outfit_preset_data.get(
                                "pend_chest_dye_scheme", {}
                            )
                            if pend_chest_dye_scheme_data:
                                player.team.char_1.outfit_preset.pend_chest_dye_scheme.scheme_index = pend_chest_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_1.outfit_preset.pend_chest_dye_scheme.is_un_lock = pend_chest_dye_scheme_data.get(
                                    "is_un_lock", False
                                )
                                # colors are empty in this case

                        player.team.char_1.gather_weapon = char_1_data.get(
                            "gather_weapon", 0
                        )

                        # Set character_appearance
                        character_appearance_data = char_1_data.get(
                            "character_appearance", {}
                        )
                        if character_appearance_data:
                            player.team.char_1.character_appearance.badge = (
                                character_appearance_data.get("badge", 0)
                            )
                            player.team.char_1.character_appearance.umbrella_id = (
                                character_appearance_data.get("umbrella_id", 0)
                            )
                            player.team.char_1.character_appearance.insect_net_instance_id = character_appearance_data.get(
                                "insect_net_instance_id", 0
                            )
                            player.team.char_1.character_appearance.logging_axe_instance_id = character_appearance_data.get(
                                "logging_axe_instance_id", 0
                            )
                            player.team.char_1.character_appearance.water_bottle_instance_id = character_appearance_data.get(
                                "water_bottle_instance_id", 0
                            )
                            player.team.char_1.character_appearance.mining_hammer_instance_id = character_appearance_data.get(
                                "mining_hammer_instance_id", 0
                            )
                            player.team.char_1.character_appearance.collection_gloves_instance_id = character_appearance_data.get(
                                "collection_gloves_instance_id", 0
                            )
                            player.team.char_1.character_appearance.fishing_rod_instance_id = character_appearance_data.get(
                                "fishing_rod_instance_id", 0
                            )

                        # Set pos
                        pos_data = char_1_data.get("pos", {})
                        if pos_data:
                            player.team.char_1.pos.x = pos_data.get("x", 0)
                            player.team.char_1.pos.y = pos_data.get("y", 0)
                            player.team.char_1.pos.z = pos_data.get("z", 0)
                            player.team.char_1.pos.decimal_places = pos_data.get(
                                "decimal_places", 0
                            )

                        # Set rot
                        rot_data = char_1_data.get("rot", {})
                        if rot_data:
                            player.team.char_1.rot.x = rot_data.get("x", 0)
                            player.team.char_1.rot.y = rot_data.get("y", 0)
                            player.team.char_1.rot.z = rot_data.get("z", 0)
                            player.team.char_1.rot.decimal_places = rot_data.get(
                                "decimal_places", 0
                            )

                        player.team.char_1.weapon_id = char_1_data.get("weapon_id", 0)
                        player.team.char_1.weapon_star = char_1_data.get(
                            "weapon_star", 0
                        )
                        player.team.char_1.char_lv = char_1_data.get("char_lv", 0)
                        player.team.char_1.char_star = char_1_data.get("char_star", 0)
                        player.team.char_1.is_dead = char_1_data.get("is_dead", False)
                        player.team.char_1.char_break_lv = char_1_data.get(
                            "char_break_lv", 0
                        )

                        # Set armors
                        for armor_data in char_1_data.get("armors", []):
                            armor = player.team.char_1.armors.add()
                            armor.armor_id = armor_data.get("armor_id", 0)
                            armor.armor_star = armor_data.get("armor_star", 0)

                        player.team.char_1.inscription_id = char_1_data.get(
                            "inscription_id", 0
                        )
                        player.team.char_1.inscription_lv = char_1_data.get(
                            "inscription_lv", 0
                        )

                        # Set posters
                        for poster_data in char_1_data.get("posters", []):
                            poster = player.team.char_1.posters.add()
                            poster.poster_id = poster_data.get("poster_id", 0)
                            poster.poster_star = poster_data.get("poster_star", 0)

                    # Set char_2
                    char_2_data = team_data.get("char_2", {})
                    if char_2_data:
                        player.team.char_2.char_id = char_2_data.get("char_id", 0)

                        # Similar processing for char_2 as char_1
                        outfit_preset_data = char_2_data.get("outfit_preset", {})
                        if outfit_preset_data:
                            player.team.char_2.outfit_preset.hat = (
                                outfit_preset_data.get("hat", 0)
                            )
                            player.team.char_2.outfit_preset.hair = (
                                outfit_preset_data.get("hair", 0)
                            )
                            player.team.char_2.outfit_preset.clothes = (
                                outfit_preset_data.get("clothes", 0)
                            )
                            player.team.char_2.outfit_preset.ornament = (
                                outfit_preset_data.get("ornament", 0)
                            )

                            # hat_dye_scheme
                            hat_dye_scheme_data = outfit_preset_data.get(
                                "hat_dye_scheme", {}
                            )
                            if hat_dye_scheme_data:
                                player.team.char_2.outfit_preset.hat_dye_scheme.scheme_index = hat_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_2.outfit_preset.hat_dye_scheme.is_un_lock = hat_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                            # hair_dye_scheme
                            hair_dye_scheme_data = outfit_preset_data.get(
                                "hair_dye_scheme", {}
                            )
                            if hair_dye_scheme_data:
                                player.team.char_2.outfit_preset.hair_dye_scheme.scheme_index = hair_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_2.outfit_preset.hair_dye_scheme.is_un_lock = hair_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                            # cloth_dye_scheme
                            cloth_dye_scheme_data = outfit_preset_data.get(
                                "cloth_dye_scheme", {}
                            )
                            if cloth_dye_scheme_data:
                                player.team.char_2.outfit_preset.cloth_dye_scheme.scheme_index = cloth_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_2.outfit_preset.cloth_dye_scheme.is_un_lock = cloth_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                            # orn_dye_scheme
                            orn_dye_scheme_data = outfit_preset_data.get(
                                "orn_dye_scheme", {}
                            )
                            if orn_dye_scheme_data:
                                player.team.char_2.outfit_preset.orn_dye_scheme.scheme_index = orn_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_2.outfit_preset.orn_dye_scheme.is_un_lock = orn_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                            # hide_info
                            hide_info_data = outfit_preset_data.get("hide_info", {})
                            if hide_info_data:
                                player.team.char_2.outfit_preset.hide_info.hide_orn = (
                                    hide_info_data.get("hide_orn", False)
                                )
                                player.team.char_2.outfit_preset.hide_info.hide_braid = hide_info_data.get(
                                    "hide_braid", False
                                )

                            player.team.char_2.outfit_preset.pend_top = (
                                outfit_preset_data.get("pend_top", 0)
                            )
                            player.team.char_2.outfit_preset.pend_chest = (
                                outfit_preset_data.get("pend_chest", 0)
                            )
                            player.team.char_2.outfit_preset.pend_pelvis = (
                                outfit_preset_data.get("pend_pelvis", 0)
                            )
                            player.team.char_2.outfit_preset.pend_up_face = (
                                outfit_preset_data.get("pend_up_face", 0)
                            )
                            player.team.char_2.outfit_preset.pend_down_face = (
                                outfit_preset_data.get("pend_down_face", 0)
                            )
                            player.team.char_2.outfit_preset.pend_left_hand = (
                                outfit_preset_data.get("pend_left_hand", 0)
                            )
                            player.team.char_2.outfit_preset.pend_right_hand = (
                                outfit_preset_data.get("pend_right_hand", 0)
                            )
                            player.team.char_2.outfit_preset.pend_left_foot = (
                                outfit_preset_data.get("pend_left_foot", 0)
                            )
                            player.team.char_2.outfit_preset.pend_right_foot = (
                                outfit_preset_data.get("pend_right_foot", 0)
                            )

                            # pend_chest_dye_scheme
                            pend_chest_dye_scheme_data = outfit_preset_data.get(
                                "pend_chest_dye_scheme", {}
                            )
                            if pend_chest_dye_scheme_data:
                                player.team.char_2.outfit_preset.pend_chest_dye_scheme.scheme_index = pend_chest_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_2.outfit_preset.pend_chest_dye_scheme.is_un_lock = pend_chest_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                        player.team.char_2.gather_weapon = char_2_data.get(
                            "gather_weapon", 0
                        )

                        # Set character_appearance
                        character_appearance_data = char_2_data.get(
                            "character_appearance", {}
                        )
                        if character_appearance_data:
                            player.team.char_2.character_appearance.badge = (
                                character_appearance_data.get("badge", 0)
                            )
                            player.team.char_2.character_appearance.umbrella_id = (
                                character_appearance_data.get("umbrella_id", 0)
                            )
                            player.team.char_2.character_appearance.insect_net_instance_id = character_appearance_data.get(
                                "insect_net_instance_id", 0
                            )
                            player.team.char_2.character_appearance.logging_axe_instance_id = character_appearance_data.get(
                                "logging_axe_instance_id", 0
                            )
                            player.team.char_2.character_appearance.water_bottle_instance_id = character_appearance_data.get(
                                "water_bottle_instance_id", 0
                            )
                            player.team.char_2.character_appearance.mining_hammer_instance_id = character_appearance_data.get(
                                "mining_hammer_instance_id", 0
                            )
                            player.team.char_2.character_appearance.collection_gloves_instance_id = character_appearance_data.get(
                                "collection_gloves_instance_id", 0
                            )
                            player.team.char_2.character_appearance.fishing_rod_instance_id = character_appearance_data.get(
                                "fishing_rod_instance_id", 0
                            )

                        # Set pos
                        pos_data = char_2_data.get("pos", {})
                        if pos_data:
                            player.team.char_2.pos.x = pos_data.get("x", 0)
                            player.team.char_2.pos.y = pos_data.get("y", 0)
                            player.team.char_2.pos.z = pos_data.get("z", 0)
                            player.team.char_2.pos.decimal_places = pos_data.get(
                                "decimal_places", 0
                            )

                        # Set rot
                        rot_data = char_2_data.get("rot", {})
                        if rot_data:
                            player.team.char_2.rot.x = rot_data.get("x", 0)
                            player.team.char_2.rot.y = rot_data.get("y", 0)
                            player.team.char_2.rot.z = rot_data.get("z", 0)
                            player.team.char_2.rot.decimal_places = rot_data.get(
                                "decimal_places", 0
                            )

                        player.team.char_2.weapon_id = char_2_data.get("weapon_id", 0)
                        player.team.char_2.weapon_star = char_2_data.get(
                            "weapon_star", 0
                        )
                        player.team.char_2.char_lv = char_2_data.get("char_lv", 0)
                        player.team.char_2.char_star = char_2_data.get("char_star", 0)
                        player.team.char_2.is_dead = char_2_data.get("is_dead", False)
                        player.team.char_2.char_break_lv = char_2_data.get(
                            "char_break_lv", 0
                        )

                        # Set armors
                        for armor_data in char_2_data.get("armors", []):
                            armor = player.team.char_2.armors.add()
                            armor.armor_id = armor_data.get("armor_id", 0)
                            armor.armor_star = armor_data.get("armor_star", 0)

                        player.team.char_2.inscription_id = char_2_data.get(
                            "inscription_id", 0
                        )
                        player.team.char_2.inscription_lv = char_2_data.get(
                            "inscription_lv", 0
                        )

                        # Set posters
                        for poster_data in char_2_data.get("posters", []):
                            poster = player.team.char_2.posters.add()
                            poster.poster_id = poster_data.get("poster_id", 0)
                            poster.poster_star = poster_data.get("poster_star", 0)

                    # Set char_3
                    char_3_data = team_data.get("char_3", {})
                    if char_3_data:
                        player.team.char_3.char_id = char_3_data.get("char_id", 0)

                        # Similar processing for char_3 as char_1
                        outfit_preset_data = char_3_data.get("outfit_preset", {})
                        if outfit_preset_data:
                            player.team.char_3.outfit_preset.hat = (
                                outfit_preset_data.get("hat", 0)
                            )
                            player.team.char_3.outfit_preset.hair = (
                                outfit_preset_data.get("hair", 0)
                            )
                            player.team.char_3.outfit_preset.clothes = (
                                outfit_preset_data.get("clothes", 0)
                            )
                            player.team.char_3.outfit_preset.ornament = (
                                outfit_preset_data.get("ornament", 0)
                            )

                            # hat_dye_scheme
                            hat_dye_scheme_data = outfit_preset_data.get(
                                "hat_dye_scheme", {}
                            )
                            if hat_dye_scheme_data:
                                player.team.char_3.outfit_preset.hat_dye_scheme.scheme_index = hat_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_3.outfit_preset.hat_dye_scheme.is_un_lock = hat_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                            # hair_dye_scheme
                            hair_dye_scheme_data = outfit_preset_data.get(
                                "hair_dye_scheme", {}
                            )
                            if hair_dye_scheme_data:
                                player.team.char_3.outfit_preset.hair_dye_scheme.scheme_index = hair_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_3.outfit_preset.hair_dye_scheme.is_un_lock = hair_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                            # cloth_dye_scheme
                            cloth_dye_scheme_data = outfit_preset_data.get(
                                "cloth_dye_scheme", {}
                            )
                            if cloth_dye_scheme_data:
                                player.team.char_3.outfit_preset.cloth_dye_scheme.scheme_index = cloth_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_3.outfit_preset.cloth_dye_scheme.is_un_lock = cloth_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                            # orn_dye_scheme
                            orn_dye_scheme_data = outfit_preset_data.get(
                                "orn_dye_scheme", {}
                            )
                            if orn_dye_scheme_data:
                                player.team.char_3.outfit_preset.orn_dye_scheme.scheme_index = orn_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_3.outfit_preset.orn_dye_scheme.is_un_lock = orn_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                            # hide_info
                            hide_info_data = outfit_preset_data.get("hide_info", {})
                            if hide_info_data:
                                player.team.char_3.outfit_preset.hide_info.hide_orn = (
                                    hide_info_data.get("hide_orn", False)
                                )
                                player.team.char_3.outfit_preset.hide_info.hide_braid = hide_info_data.get(
                                    "hide_braid", False
                                )

                            player.team.char_3.outfit_preset.pend_top = (
                                outfit_preset_data.get("pend_top", 0)
                            )
                            player.team.char_3.outfit_preset.pend_chest = (
                                outfit_preset_data.get("pend_chest", 0)
                            )
                            player.team.char_3.outfit_preset.pend_pelvis = (
                                outfit_preset_data.get("pend_pelvis", 0)
                            )
                            player.team.char_3.outfit_preset.pend_up_face = (
                                outfit_preset_data.get("pend_up_face", 0)
                            )
                            player.team.char_3.outfit_preset.pend_down_face = (
                                outfit_preset_data.get("pend_down_face", 0)
                            )
                            player.team.char_3.outfit_preset.pend_left_hand = (
                                outfit_preset_data.get("pend_left_hand", 0)
                            )
                            player.team.char_3.outfit_preset.pend_right_hand = (
                                outfit_preset_data.get("pend_right_hand", 0)
                            )
                            player.team.char_3.outfit_preset.pend_left_foot = (
                                outfit_preset_data.get("pend_left_foot", 0)
                            )
                            player.team.char_3.outfit_preset.pend_right_foot = (
                                outfit_preset_data.get("pend_right_foot", 0)
                            )

                            # pend_chest_dye_scheme
                            pend_chest_dye_scheme_data = outfit_preset_data.get(
                                "pend_chest_dye_scheme", {}
                            )
                            if pend_chest_dye_scheme_data:
                                player.team.char_3.outfit_preset.pend_chest_dye_scheme.scheme_index = pend_chest_dye_scheme_data.get(
                                    "scheme_index", 0
                                )
                                player.team.char_3.outfit_preset.pend_chest_dye_scheme.is_un_lock = pend_chest_dye_scheme_data.get(
                                    "is_un_lock", False
                                )

                        player.team.char_3.gather_weapon = char_3_data.get(
                            "gather_weapon", 0
                        )

                        # Set character_appearance
                        character_appearance_data = char_3_data.get(
                            "character_appearance", {}
                        )
                        if character_appearance_data:
                            player.team.char_3.character_appearance.badge = (
                                character_appearance_data.get("badge", 0)
                            )
                            player.team.char_3.character_appearance.umbrella_id = (
                                character_appearance_data.get("umbrella_id", 0)
                            )
                            player.team.char_3.character_appearance.insect_net_instance_id = character_appearance_data.get(
                                "insect_net_instance_id", 0
                            )
                            player.team.char_3.character_appearance.logging_axe_instance_id = character_appearance_data.get(
                                "logging_axe_instance_id", 0
                            )
                            player.team.char_3.character_appearance.water_bottle_instance_id = character_appearance_data.get(
                                "water_bottle_instance_id", 0
                            )
                            player.team.char_3.character_appearance.mining_hammer_instance_id = character_appearance_data.get(
                                "mining_hammer_instance_id", 0
                            )
                            player.team.char_3.character_appearance.collection_gloves_instance_id = character_appearance_data.get(
                                "collection_gloves_instance_id", 0
                            )
                            player.team.char_3.character_appearance.fishing_rod_instance_id = character_appearance_data.get(
                                "fishing_rod_instance_id", 0
                            )

                        # Set pos
                        pos_data = char_3_data.get("pos", {})
                        if pos_data:
                            player.team.char_3.pos.x = pos_data.get("x", 0)
                            player.team.char_3.pos.y = pos_data.get("y", 0)
                            player.team.char_3.pos.z = pos_data.get("z", 0)
                            player.team.char_3.pos.decimal_places = pos_data.get(
                                "decimal_places", 0
                            )

                        # Set rot
                        rot_data = char_3_data.get("rot", {})
                        if rot_data:
                            player.team.char_3.rot.x = rot_data.get("x", 0)
                            player.team.char_3.rot.y = rot_data.get("y", 0)
                            player.team.char_3.rot.z = rot_data.get("z", 0)
                            player.team.char_3.rot.decimal_places = rot_data.get(
                                "decimal_places", 0
                            )

                        player.team.char_3.weapon_id = char_3_data.get("weapon_id", 0)
                        player.team.char_3.weapon_star = char_3_data.get(
                            "weapon_star", 0
                        )
                        player.team.char_3.char_lv = char_3_data.get("char_lv", 0)
                        player.team.char_3.char_star = char_3_data.get("char_star", 0)
                        player.team.char_3.is_dead = char_3_data.get("is_dead", False)
                        player.team.char_3.char_break_lv = char_3_data.get(
                            "char_break_lv", 0
                        )

                        # Set armors
                        for armor_data in char_3_data.get("armors", []):
                            armor = player.team.char_3.armors.add()
                            armor.armor_id = armor_data.get("armor_id", 0)
                            armor.armor_star = armor_data.get("armor_star", 0)

                        player.team.char_3.inscription_id = char_3_data.get(
                            "inscription_id", 0
                        )
                        player.team.char_3.inscription_lv = char_3_data.get(
                            "inscription_lv", 0
                        )

                        # Set posters
                        for poster_data in char_3_data.get("posters", []):
                            poster = player.team.char_3.posters.add()
                            poster.poster_id = poster_data.get("poster_id", 0)
                            poster.poster_star = poster_data.get("poster_star", 0)

                # Set status
                status_data = player_data.get("status", {})
                if status_data:
                    player.status.id = status_data.get("id", 0)
                    player.status.value_1 = status_data.get("value_1", 0)
                    player.status.value_2 = status_data.get("value_2", 0)
                    player.status.value_3 = status_data.get("value_3", 0)
                    player.status.value_4 = status_data.get("value_4", 0)
                    player.status.value_5 = status_data.get("value_5", 0)

                # Set food_buff_ids
                for buff_id in player_data.get("food_buff_ids", []):
                    player.food_buff_ids.append(buff_id)

                # Set global_buff_ids
                for buff_id in player_data.get("global_buff_ids", []):
                    player.global_buff_ids.append(buff_id)

                player.is_birthday = player_data.get("is_birthday", False)

            # 频道标签
            rsp.data.channel_id = data_obj.get("channel_id", 0)

            # Set tod_time
            rsp.data.tod_time = data_obj.get("tod_time", 0)

            # Set scene_garden_data
            scene_garden_data = data_obj.get("scene_garden_data", {})
            if scene_garden_data:
                # Set garden_furniture_info_map (empty in this case)
                # No garden furniture info in the sample data
                garden_furniture_info_map = scene_garden_data.get(
                    "garden_furniture_info_map", {}
                )
                # Ensure garden_furniture_info_map is a dict before iterating
                if isinstance(garden_furniture_info_map, dict):
                    for key, value in garden_furniture_info_map.items():
                        furniture_details = (
                            rsp.data.scene_garden_data.garden_furniture_info_map[key]
                        )
                        furniture_details.furniture_id = value.get("furniture_id", 0)
                        furniture_details.pos.x = value.get("pos", {}).get("x", 0)
                        furniture_details.pos.y = value.get("pos", {}).get("y", 0)
                        furniture_details.pos.z = value.get("pos", {}).get("z", 0)
                        furniture_details.pos.decimal_places = value.get("pos", {}).get(
                            "decimal_places", 0
                        )
                        furniture_details.rotation.x = value.get("rotation", {}).get(
                            "x", 0
                        )
                        furniture_details.rotation.y = value.get("rotation", {}).get(
                            "y", 0
                        )
                        furniture_details.rotation.z = value.get("rotation", {}).get(
                            "z", 0
                        )
                        furniture_details.rotation.decimal_places = value.get(
                            "rotation", {}
                        ).get("decimal_places", 0)

                rsp.data.scene_garden_data.likes_num = scene_garden_data.get(
                    "likes_num", 0
                )
                rsp.data.scene_garden_data.access_player_num = scene_garden_data.get(
                    "access_player_num", 0
                )
                rsp.data.scene_garden_data.left_like_num = scene_garden_data.get(
                    "left_like_num", 0
                )
                rsp.data.scene_garden_data.garden_name = scene_garden_data.get(
                    "garden_name", ""
                )
                rsp.data.scene_garden_data.furniture_current_point_num = (
                    scene_garden_data.get("furniture_current_point_num", 0)
                )

                # Set furniture_player_map (empty in this case)
                # No furniture player map in the sample data
                furniture_player_map = scene_garden_data.get("furniture_player_map", {})
                # Ensure furniture_player_map is a dict before iterating
                if isinstance(furniture_player_map, dict):
                    for key, value in furniture_player_map.items():
                        rsp.data.scene_garden_data.furniture_player_map[key] = value

                # Set other_player_furniture_info_map (empty in this case)
                # No other player furniture info in the sample data
                other_player_furniture_info_map = scene_garden_data.get(
                    "other_player_furniture_info_map", {}
                )
                # Ensure other_player_furniture_info_map is a dict before iterating
                if isinstance(other_player_furniture_info_map, dict):
                    for key, value in other_player_furniture_info_map.items():
                        rsp.data.scene_garden_data.other_player_furniture_info_map[
                            key
                        ] = value

                # Set player_handing_furniture_info_map (empty in this case)
                # No player handing furniture info in the sample data
                player_handing_furniture_info_map = scene_garden_data.get(
                    "player_handing_furniture_info_map", {}
                )
                # Ensure player_handing_furniture_info_map is a dict before iterating
                if isinstance(player_handing_furniture_info_map, dict):
                    for key, value in player_handing_furniture_info_map.items():
                        rsp.data.scene_garden_data.player_handing_furniture_info_map[
                            key
                        ] = value

            # Set camp_fires (empty in this case)
            # No camp fires in the sample data
            for camp_fire_data in data_obj.get("camp_fires", []):
                camp_fire = rsp.data.camp_fires.add()
                camp_fire.pos.x = camp_fire_data.get("pos", {}).get("x", 0)
                camp_fire.pos.y = camp_fire_data.get("pos", {}).get("y", 0)
                camp_fire.pos.z = camp_fire_data.get("pos", {}).get("z", 0)
                camp_fire.pos.decimal_places = camp_fire_data.get("pos", {}).get(
                    "decimal_places", 0
                )
                camp_fire.rot.x = camp_fire_data.get("rot", {}).get("x", 0)
                camp_fire.rot.y = camp_fire_data.get("rot", {}).get("y", 0)
                camp_fire.rot.z = camp_fire_data.get("rot", {}).get("z", 0)
                camp_fire.rot.decimal_places = camp_fire_data.get("rot", {}).get(
                    "decimal_places", 0
                )
                camp_fire.id = camp_fire_data.get("id", 0)
                camp_fire.player_id = camp_fire_data.get("player_id", 0)
                camp_fire.place_time = camp_fire_data.get("place_time", 0)
                camp_fire.action_id = camp_fire_data.get("action_id", 0)

            # Set weather_type
            rsp.data.weather_type = data_obj.get("weather_type", 0)

            # Set channel_label
            rsp.data.channel_label = data_obj.get("channel_label", 0)

            # Set fireworks_info
            fireworks_info_data = data_obj.get("fireworks_info", {})
            if fireworks_info_data:
                rsp.data.fireworks_info.fireworks_id = fireworks_info_data.get(
                    "fireworks_id", 0
                )
                rsp.data.fireworks_info.fireworks_duration_time = (
                    fireworks_info_data.get("fireworks_duration_time", 0)
                )
                rsp.data.fireworks_info.fireworks_start_time = fireworks_info_data.get(
                    "fireworks_start_time", 0
                )

            # Set mp_beacons (empty in this case)
            # No mp beacons in the sample data
            for mp_beacon_data in data_obj.get("mp_beacons", []):
                mp_beacon = rsp.data.mp_beacons.add()
                mp_beacon.owner_id = mp_beacon_data.get("owner_id", 0)
                mp_beacon.team_id = mp_beacon_data.get("team_id", 0)
                mp_beacon.status = mp_beacon_data.get("status", 0)
                mp_beacon.position.x = mp_beacon_data.get("position", {}).get("x", 0)
                mp_beacon.position.y = mp_beacon_data.get("position", {}).get("y", 0)
                mp_beacon.position.z = mp_beacon_data.get("position", {}).get("z", 0)
                mp_beacon.position.decimal_places = mp_beacon_data.get(
                    "position", {}
                ).get("decimal_places", 0)
                mp_beacon.rotation.x = mp_beacon_data.get("rotation", {}).get("x", 0)
                mp_beacon.rotation.y = mp_beacon_data.get("rotation", {}).get("y", 0)
                mp_beacon.rotation.z = mp_beacon_data.get("rotation", {}).get("z", 0)
                mp_beacon.rotation.decimal_places = mp_beacon_data.get(
                    "rotation", {}
                ).get("decimal_places", 0)
                mp_beacon.count_down_from_sec = mp_beacon_data.get(
                    "count_down_from_sec", 0
                )
                mp_beacon.channel_id = mp_beacon_data.get("channel_id", 0)
                mp_beacon.scene_id = mp_beacon_data.get("scene_id", 0)
                mp_beacon.mode_id = mp_beacon_data.get("mode_id", 0)
                # Note: members map not handled in this sample data

            # Set network_event (empty in this case)
            # No network events in the sample data
            for network_event_data in data_obj.get("network_event", []):
                network_event = rsp.data.network_event.add()
                network_event.object_id = network_event_data.get("object_id", 0)
                network_event.event_id = network_event_data.get("event_id", 0)
                # Note: param repeated field not handled in this sample data

            # Set placed_characters (empty in this case)
            # No placed characters in the sample data
            for placed_character_data in data_obj.get("placed_characters", []):
                placed_character = rsp.data.placed_characters.add()
                placed_character.character_id = placed_character_data.get(
                    "character_id", 0
                )
                # Note: outfit_preset and furniture_id not handled in this sample data

            # Set moon_spots (empty in this case)
            # No moon spots in the sample data
            for moon_spot_data in data_obj.get("moon_spots", []):
                moon_spot = rsp.data.moon_spots.add()
                moon_spot.id = moon_spot_data.get("id", 0)
                moon_spot.instance_id = moon_spot_data.get("instance_id", 0)
                moon_spot.pos.x = moon_spot_data.get("pos", {}).get("x", 0)
                moon_spot.pos.y = moon_spot_data.get("pos", {}).get("y", 0)
                moon_spot.pos.z = moon_spot_data.get("pos", {}).get("z", 0)
                moon_spot.pos.decimal_places = moon_spot_data.get("pos", {}).get(
                    "decimal_places", 0
                )
                moon_spot.rot.x = moon_spot_data.get("rot", {}).get("x", 0)
                moon_spot.rot.y = moon_spot_data.get("rot", {}).get("y", 0)
                moon_spot.rot.z = moon_spot_data.get("rot", {}).get("z", 0)
                moon_spot.rot.decimal_places = moon_spot_data.get("rot", {}).get(
                    "decimal_places", 0
                )
                moon_spot.create_time = moon_spot_data.get("create_time", 0)

            # Set room_decor_list (empty in this case)
            # No room decor list in the sample data
            for room_decor_data in data_obj.get("room_decor_list", []):
                room_decor = rsp.data.room_decor_list.add()
                room_decor.decor_id = room_decor_data.get("decor_id", 0)
                room_decor.pos_id = room_decor_data.get("pos_id", 0)
                room_decor.item_id = room_decor_data.get("item_id", 0)

            # Set drop_items
            for drop_item_data in data_obj.get("drop_items", []):
                drop_item = rsp.data.drop_items.add()
                drop_item.index = drop_item_data.get("index", 0)
                # Set items in drop_item
                items_data = drop_item_data.get("items", [])
                # Ensure items_data is a list before iterating
                if isinstance(items_data, list):
                    for item_data in items_data:
                        item = drop_item.items.add()
                        item.item_id = item_data.get("item_id", 0)
                        item.item_num = item_data.get("item_num", 0)
                        item.enhance_level = item_data.get("enhance_level", 0)
                        item.exp = item_data.get("exp", 0)
                        item.total_exp = item_data.get("total_exp", 0)
                        # Set main_prop in item
                        main_prop_data = item_data.get("main_prop", {})
                        if main_prop_data:
                            item.main_prop.prop_type = main_prop_data.get(
                                "prop_type", 0
                            )
                            item.main_prop.prop_value = main_prop_data.get(
                                "prop_value", 0
                            )
                        # Set sub_props in item
                        for sub_prop_data in item_data.get("sub_props", []):
                            sub_prop = item.sub_props.add()
                            sub_prop.prop_type = sub_prop_data.get("prop_type", 0)
                            sub_prop.prop_value = sub_prop_data.get("prop_value", 0)
                        item.level = item_data.get("level", 0)
                        item.star = item_data.get("star", 0)
                        item.quality = item_data.get("quality", 0)
                        item.lock = item_data.get("lock", False)

            # Set flags
            for flag_data in data_obj.get("flags", []):
                flag = rsp.data.flags.add()
                flag.battle_id = flag_data.get("battle_id", 0)
                flag.state = flag_data.get("state", 0)
                flag.type = flag_data.get("type", 0)
                flag.finish_times = flag_data.get("finish_times", 0)
                flag.voice_id = flag_data.get("voice_id", 0)

            # Set region_voices
            for region_voice_id in data_obj.get("region_voices", []):
                rsp.data.region_voices.append(region_voice_id)

            # Set soccer_position
            soccer_position_data = data_obj.get("soccer_position", {})
            if soccer_position_data:
                rsp.data.soccer_position.position.x = soccer_position_data.get(
                    "position", {}
                ).get("x", 0)
                rsp.data.soccer_position.position.y = soccer_position_data.get(
                    "position", {}
                ).get("y", 0)
                rsp.data.soccer_position.position.z = soccer_position_data.get(
                    "position", {}
                ).get("z", 0)
                rsp.data.soccer_position.position.decimal_places = (
                    soccer_position_data.get("position", {}).get("decimal_places", 0)
                )

            # Set chair_info_list
            for chair_info_data in data_obj.get("chair_info_list", []):
                chair_info = rsp.data.chair_info_list.add()
                chair_info.chair_id = chair_info_data.get("chair_id", 0)
                chair_info.seat_id = chair_info_data.get("seat_id", 0)
                chair_info.player_id = chair_info_data.get("player_id", 0)

            # Set dungeons
            for dungeon_data in data_obj.get("dungeons", []):
                dungeon = rsp.data.dungeons.add()
                dungeon.dungeon_id = dungeon_data.get("dungeon_id", 0)
                dungeon.all_task_finished = dungeon_data.get("all_task_finished", False)
                dungeon.enter_times = dungeon_data.get("enter_times", 0)
                dungeon.exit_times = dungeon_data.get("exit_times", 0)
                dungeon.finish_times = dungeon_data.get("finish_times", 0)
                # Set coins in dungeon
                for coin in dungeon_data.get("coins", []):
                    dungeon.coins.append(coin)
                dungeon.last_finish_time = dungeon_data.get("last_finish_time", 0)
                dungeon.task_finish_reward = dungeon_data.get("task_finish_reward", 0)
                dungeon.star_reward = dungeon_data.get("star_reward", 0)
                # Set monsters in dungeon
                for monster in dungeon_data.get("monsters", []):
                    dungeon.monsters.append(monster)
                dungeon.char_1 = dungeon_data.get("char_1", 0)
                dungeon.char_2 = dungeon_data.get("char_2", 0)
                dungeon.char_3 = dungeon_data.get("char_3", 0)
                dungeon.last_enter_time = dungeon_data.get("last_enter_time", 0)
                # Set pos in dungeon
                pos_data = dungeon_data.get("pos", {})
                if pos_data:
                    dungeon.pos.x = pos_data.get("x", 0)
                    dungeon.pos.y = pos_data.get("y", 0)
                    dungeon.pos.z = pos_data.get("z", 0)
                    dungeon.pos.decimal_places = pos_data.get("decimal_places", 0)
                # Set rot in dungeon
                rot_data = dungeon_data.get("rot", {})
                if rot_data:
                    dungeon.rot.x = rot_data.get("x", 0)
                    dungeon.rot.y = rot_data.get("y", 0)
                    dungeon.rot.z = rot_data.get("z", 0)
                    dungeon.rot.decimal_places = rot_data.get("decimal_places", 0)
                dungeon.is_open_secret_box = dungeon_data.get(
                    "is_open_secret_box", False
                )

            # Set flag_ids
            for flag_id in data_obj.get("flag_ids", []):
                rsp.data.flag_ids.append(flag_id)

            # Set current_gather_group_id
            rsp.data.current_gather_group_id = data_obj.get(
                "current_gather_group_id", 0
            )

        # Send response
        session.send(CmdId.SceneDataNotice, rsp, packet_id)
        print(rsp.data.players)
