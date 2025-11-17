from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import json
import os

import proto.OverField_pb2 as ServerSceneSyncDataNotice_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ServerSceneSyncDataNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # Load hardcoded data from JSON file
        json_file_path = os.path.join(os.path.dirname(__file__), '..', 'tmp', 'data', 'ServerSceneSyncDataNotice.json')
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        parsed_result = json_data.get("parsed_result", {})
        
        # Create response message
        rsp = ServerSceneSyncDataNotice_pb2.ServerSceneSyncDataNotice()
        
        # Set status
        rsp.status = parsed_result.get("status", 1)
        
        # Set data
        data_list = parsed_result.get("data", [])
        for data_obj in data_list:
            server_data = rsp.data.add()
            server_data.player_id = data_obj.get("player_id", 0)
            
            # Set server_data
            server_data_list = data_obj.get("server_data", [])
            for server_data_obj in server_data_list:
                server_data_entry = server_data.server_data.add()
                server_data_entry.action_type = server_data_obj.get("action_type", 0)
                
                # Set player
                player_data = server_data_obj.get("player", {})
                if player_data:
                    server_data_entry.player.player_id = player_data.get("player_id", 0)
                    server_data_entry.player.player_name = player_data.get("player_name", "")
                    
                    # Set team
                    team_data = player_data.get("team", {})
                    if team_data:
                        # Set char_1
                        char_1_data = team_data.get("char_1", {})
                        if char_1_data:
                            server_data_entry.player.team.char_1.char_id = char_1_data.get("char_id", 0)
                            
                            # Set outfit_preset
                            outfit_preset_data = char_1_data.get("outfit_preset", {})
                            if outfit_preset_data:
                                server_data_entry.player.team.char_1.outfit_preset.hat = outfit_preset_data.get("hat", 0)
                                server_data_entry.player.team.char_1.outfit_preset.hair = outfit_preset_data.get("hair", 0)
                                server_data_entry.player.team.char_1.outfit_preset.clothes = outfit_preset_data.get("clothes", 0)
                                server_data_entry.player.team.char_1.outfit_preset.ornament = outfit_preset_data.get("ornament", 0)
                                
                                # hat_dye_scheme
                                hat_dye_scheme_data = outfit_preset_data.get("hat_dye_scheme", {})
                                if hat_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.hat_dye_scheme.scheme_index = hat_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.hat_dye_scheme.is_un_lock = hat_dye_scheme_data.get("is_un_lock", False)
                                    # Set colors
                                    for color_data in hat_dye_scheme_data.get("colors", []):
                                        color = server_data_entry.player.team.char_1.outfit_preset.hat_dye_scheme.colors.add()
                                        color.pos = color_data.get("pos", 0)
                                        color.red = color_data.get("red", 0)
                                        color.green = color_data.get("green", 0)
                                        color.blue = color_data.get("blue", 0)
                                
                                # hair_dye_scheme
                                hair_dye_scheme_data = outfit_preset_data.get("hair_dye_scheme", {})
                                if hair_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.hair_dye_scheme.scheme_index = hair_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.hair_dye_scheme.is_un_lock = hair_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # cloth_dye_scheme
                                cloth_dye_scheme_data = outfit_preset_data.get("cloth_dye_scheme", {})
                                if cloth_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.cloth_dye_scheme.scheme_index = cloth_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.cloth_dye_scheme.is_un_lock = cloth_dye_scheme_data.get("is_un_lock", False)
                                    # Set colors
                                    for color_data in cloth_dye_scheme_data.get("colors", []):
                                        color = server_data_entry.player.team.char_1.outfit_preset.cloth_dye_scheme.colors.add()
                                        color.pos = color_data.get("pos", 0)
                                        color.red = color_data.get("red", 0)
                                        color.green = color_data.get("green", 0)
                                        color.blue = color_data.get("blue", 0)
                                
                                # orn_dye_scheme
                                orn_dye_scheme_data = outfit_preset_data.get("orn_dye_scheme", {})
                                if orn_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.orn_dye_scheme.scheme_index = orn_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.orn_dye_scheme.is_un_lock = orn_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # hide_info
                                hide_info_data = outfit_preset_data.get("hide_info", {})
                                if hide_info_data:
                                    server_data_entry.player.team.char_1.outfit_preset.hide_info.hide_orn = hide_info_data.get("hide_orn", False)
                                    server_data_entry.player.team.char_1.outfit_preset.hide_info.hide_braid = hide_info_data.get("hide_braid", False)
                                
                                server_data_entry.player.team.char_1.outfit_preset.pend_top = outfit_preset_data.get("pend_top", 0)
                                server_data_entry.player.team.char_1.outfit_preset.pend_chest = outfit_preset_data.get("pend_chest", 0)
                                server_data_entry.player.team.char_1.outfit_preset.pend_pelvis = outfit_preset_data.get("pend_pelvis", 0)
                                server_data_entry.player.team.char_1.outfit_preset.pend_up_face = outfit_preset_data.get("pend_up_face", 0)
                                server_data_entry.player.team.char_1.outfit_preset.pend_down_face = outfit_preset_data.get("pend_down_face", 0)
                                server_data_entry.player.team.char_1.outfit_preset.pend_left_hand = outfit_preset_data.get("pend_left_hand", 0)
                                server_data_entry.player.team.char_1.outfit_preset.pend_right_hand = outfit_preset_data.get("pend_right_hand", 0)
                                server_data_entry.player.team.char_1.outfit_preset.pend_left_foot = outfit_preset_data.get("pend_left_foot", 0)
                                server_data_entry.player.team.char_1.outfit_preset.pend_right_foot = outfit_preset_data.get("pend_right_foot", 0)
                                
                                # pend_top_dye_scheme
                                pend_top_dye_scheme_data = outfit_preset_data.get("pend_top_dye_scheme", {})
                                if pend_top_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_top_dye_scheme.scheme_index = pend_top_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_top_dye_scheme.is_un_lock = pend_top_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # pend_chest_dye_scheme
                                pend_chest_dye_scheme_data = outfit_preset_data.get("pend_chest_dye_scheme", {})
                                if pend_chest_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_chest_dye_scheme.scheme_index = pend_chest_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_chest_dye_scheme.is_un_lock = pend_chest_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # pend_pelvis_dye_scheme
                                pend_pelvis_dye_scheme_data = outfit_preset_data.get("pend_pelvis_dye_scheme", {})
                                if pend_pelvis_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_pelvis_dye_scheme.scheme_index = pend_pelvis_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_pelvis_dye_scheme.is_un_lock = pend_pelvis_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # pend_up_face_dye_scheme
                                pend_up_face_dye_scheme_data = outfit_preset_data.get("pend_up_face_dye_scheme", {})
                                if pend_up_face_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_up_face_dye_scheme.scheme_index = pend_up_face_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_up_face_dye_scheme.is_un_lock = pend_up_face_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # pend_down_face_dye_scheme
                                pend_down_face_dye_scheme_data = outfit_preset_data.get("pend_down_face_dye_scheme", {})
                                if pend_down_face_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_down_face_dye_scheme.scheme_index = pend_down_face_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_down_face_dye_scheme.is_un_lock = pend_down_face_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # pend_left_hand_dye_scheme
                                pend_left_hand_dye_scheme_data = outfit_preset_data.get("pend_left_hand_dye_scheme", {})
                                if pend_left_hand_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_left_hand_dye_scheme.scheme_index = pend_left_hand_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_left_hand_dye_scheme.is_un_lock = pend_left_hand_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # pend_right_hand_dye_scheme
                                pend_right_hand_dye_scheme_data = outfit_preset_data.get("pend_right_hand_dye_scheme", {})
                                if pend_right_hand_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_right_hand_dye_scheme.scheme_index = pend_right_hand_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_right_hand_dye_scheme.is_un_lock = pend_right_hand_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # pend_left_foot_dye_scheme
                                pend_left_foot_dye_scheme_data = outfit_preset_data.get("pend_left_foot_dye_scheme", {})
                                if pend_left_foot_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_left_foot_dye_scheme.scheme_index = pend_left_foot_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_left_foot_dye_scheme.is_un_lock = pend_left_foot_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                                
                                # pend_right_foot_dye_scheme
                                pend_right_foot_dye_scheme_data = outfit_preset_data.get("pend_right_foot_dye_scheme", {})
                                if pend_right_foot_dye_scheme_data:
                                    server_data_entry.player.team.char_1.outfit_preset.pend_right_foot_dye_scheme.scheme_index = pend_right_foot_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_1.outfit_preset.pend_right_foot_dye_scheme.is_un_lock = pend_right_foot_dye_scheme_data.get("is_un_lock", False)
                                    # colors are empty in this case
                            
                            server_data_entry.player.team.char_1.gather_weapon = char_1_data.get("gather_weapon", 0)
                            
                            # Set character_appearance
                            character_appearance_data = char_1_data.get("character_appearance", {})
                            if character_appearance_data:
                                server_data_entry.player.team.char_1.character_appearance.badge = character_appearance_data.get("badge", 0)
                                server_data_entry.player.team.char_1.character_appearance.umbrella_id = character_appearance_data.get("umbrella_id", 0)
                                server_data_entry.player.team.char_1.character_appearance.insect_net_instance_id = character_appearance_data.get("insect_net_instance_id", 0)
                                server_data_entry.player.team.char_1.character_appearance.logging_axe_instance_id = character_appearance_data.get("logging_axe_instance_id", 0)
                                server_data_entry.player.team.char_1.character_appearance.water_bottle_instance_id = character_appearance_data.get("water_bottle_instance_id", 0)
                                server_data_entry.player.team.char_1.character_appearance.mining_hammer_instance_id = character_appearance_data.get("mining_hammer_instance_id", 0)
                                server_data_entry.player.team.char_1.character_appearance.collection_gloves_instance_id = character_appearance_data.get("collection_gloves_instance_id", 0)
                                server_data_entry.player.team.char_1.character_appearance.fishing_rod_instance_id = character_appearance_data.get("fishing_rod_instance_id", 0)
                            
                            # Set pos
                            pos_data = char_1_data.get("pos", {})
                            if pos_data:
                                server_data_entry.player.team.char_1.pos.x = pos_data.get("x", 0)
                                server_data_entry.player.team.char_1.pos.y = pos_data.get("y", 0)
                                server_data_entry.player.team.char_1.pos.z = pos_data.get("z", 0)
                                server_data_entry.player.team.char_1.pos.decimal_places = pos_data.get("decimal_places", 0)
                            
                            # Set rot
                            rot_data = char_1_data.get("rot", {})
                            if rot_data:
                                server_data_entry.player.team.char_1.rot.x = rot_data.get("x", 0)
                                server_data_entry.player.team.char_1.rot.y = rot_data.get("y", 0)
                                server_data_entry.player.team.char_1.rot.z = rot_data.get("z", 0)
                                server_data_entry.player.team.char_1.rot.decimal_places = rot_data.get("decimal_places", 0)
                            
                            server_data_entry.player.team.char_1.weapon_id = char_1_data.get("weapon_id", 0)
                            server_data_entry.player.team.char_1.weapon_star = char_1_data.get("weapon_star", 0)
                            server_data_entry.player.team.char_1.char_lv = char_1_data.get("char_lv", 0)
                            server_data_entry.player.team.char_1.char_star = char_1_data.get("char_star", 0)
                            server_data_entry.player.team.char_1.is_dead = char_1_data.get("is_dead", False)
                            server_data_entry.player.team.char_1.char_break_lv = char_1_data.get("char_break_lv", 0)
                            
                            # Set armors
                            for armor_data in char_1_data.get("armors", []):
                                armor = server_data_entry.player.team.char_1.armors.add()
                                armor.armor_id = armor_data.get("armor_id", 0)
                                armor.armor_star = armor_data.get("armor_star", 0)
                            
                            server_data_entry.player.team.char_1.inscription_id = char_1_data.get("inscription_id", 0)
                            server_data_entry.player.team.char_1.inscription_lv = char_1_data.get("inscription_lv", 0)
                            
                            # Set posters
                            for poster_data in char_1_data.get("posters", []):
                                poster = server_data_entry.player.team.char_1.posters.add()
                                poster.poster_id = poster_data.get("poster_id", 0)
                                poster.poster_star = poster_data.get("poster_star", 0)
                        
                        # Set char_2
                        char_2_data = team_data.get("char_2", {})
                        if char_2_data:
                            server_data_entry.player.team.char_2.char_id = char_2_data.get("char_id", 0)
                            
                            # Set outfit_preset
                            outfit_preset_data = char_2_data.get("outfit_preset", {})
                            if outfit_preset_data:
                                server_data_entry.player.team.char_2.outfit_preset.hat = outfit_preset_data.get("hat", 0)
                                server_data_entry.player.team.char_2.outfit_preset.hair = outfit_preset_data.get("hair", 0)
                                server_data_entry.player.team.char_2.outfit_preset.clothes = outfit_preset_data.get("clothes", 0)
                                server_data_entry.player.team.char_2.outfit_preset.ornament = outfit_preset_data.get("ornament", 0)
                                
                                # hat_dye_scheme
                                hat_dye_scheme_data = outfit_preset_data.get("hat_dye_scheme", {})
                                if hat_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.hat_dye_scheme.scheme_index = hat_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.hat_dye_scheme.is_un_lock = hat_dye_scheme_data.get("is_un_lock", False)
                                
                                # hair_dye_scheme
                                hair_dye_scheme_data = outfit_preset_data.get("hair_dye_scheme", {})
                                if hair_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.hair_dye_scheme.scheme_index = hair_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.hair_dye_scheme.is_un_lock = hair_dye_scheme_data.get("is_un_lock", False)
                                
                                # cloth_dye_scheme
                                cloth_dye_scheme_data = outfit_preset_data.get("cloth_dye_scheme", {})
                                if cloth_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.cloth_dye_scheme.scheme_index = cloth_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.cloth_dye_scheme.is_un_lock = cloth_dye_scheme_data.get("is_un_lock", False)
                                
                                # orn_dye_scheme
                                orn_dye_scheme_data = outfit_preset_data.get("orn_dye_scheme", {})
                                if orn_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.orn_dye_scheme.scheme_index = orn_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.orn_dye_scheme.is_un_lock = orn_dye_scheme_data.get("is_un_lock", False)
                                
                                # hide_info
                                hide_info_data = outfit_preset_data.get("hide_info", {})
                                if hide_info_data:
                                    server_data_entry.player.team.char_2.outfit_preset.hide_info.hide_orn = hide_info_data.get("hide_orn", False)
                                    server_data_entry.player.team.char_2.outfit_preset.hide_info.hide_braid = hide_info_data.get("hide_braid", False)
                                
                                server_data_entry.player.team.char_2.outfit_preset.pend_top = outfit_preset_data.get("pend_top", 0)
                                server_data_entry.player.team.char_2.outfit_preset.pend_chest = outfit_preset_data.get("pend_chest", 0)
                                server_data_entry.player.team.char_2.outfit_preset.pend_pelvis = outfit_preset_data.get("pend_pelvis", 0)
                                server_data_entry.player.team.char_2.outfit_preset.pend_up_face = outfit_preset_data.get("pend_up_face", 0)
                                server_data_entry.player.team.char_2.outfit_preset.pend_down_face = outfit_preset_data.get("pend_down_face", 0)
                                server_data_entry.player.team.char_2.outfit_preset.pend_left_hand = outfit_preset_data.get("pend_left_hand", 0)
                                server_data_entry.player.team.char_2.outfit_preset.pend_right_hand = outfit_preset_data.get("pend_right_hand", 0)
                                server_data_entry.player.team.char_2.outfit_preset.pend_left_foot = outfit_preset_data.get("pend_left_foot", 0)
                                server_data_entry.player.team.char_2.outfit_preset.pend_right_foot = outfit_preset_data.get("pend_right_foot", 0)
                                
                                # pend_top_dye_scheme
                                pend_top_dye_scheme_data = outfit_preset_data.get("pend_top_dye_scheme", {})
                                if pend_top_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_top_dye_scheme.scheme_index = pend_top_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_top_dye_scheme.is_un_lock = pend_top_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_chest_dye_scheme
                                pend_chest_dye_scheme_data = outfit_preset_data.get("pend_chest_dye_scheme", {})
                                if pend_chest_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_chest_dye_scheme.scheme_index = pend_chest_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_chest_dye_scheme.is_un_lock = pend_chest_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_pelvis_dye_scheme
                                pend_pelvis_dye_scheme_data = outfit_preset_data.get("pend_pelvis_dye_scheme", {})
                                if pend_pelvis_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_pelvis_dye_scheme.scheme_index = pend_pelvis_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_pelvis_dye_scheme.is_un_lock = pend_pelvis_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_up_face_dye_scheme
                                pend_up_face_dye_scheme_data = outfit_preset_data.get("pend_up_face_dye_scheme", {})
                                if pend_up_face_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_up_face_dye_scheme.scheme_index = pend_up_face_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_up_face_dye_scheme.is_un_lock = pend_up_face_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_down_face_dye_scheme
                                pend_down_face_dye_scheme_data = outfit_preset_data.get("pend_down_face_dye_scheme", {})
                                if pend_down_face_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_down_face_dye_scheme.scheme_index = pend_down_face_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_down_face_dye_scheme.is_un_lock = pend_down_face_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_left_hand_dye_scheme
                                pend_left_hand_dye_scheme_data = outfit_preset_data.get("pend_left_hand_dye_scheme", {})
                                if pend_left_hand_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_left_hand_dye_scheme.scheme_index = pend_left_hand_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_left_hand_dye_scheme.is_un_lock = pend_left_hand_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_right_hand_dye_scheme
                                pend_right_hand_dye_scheme_data = outfit_preset_data.get("pend_right_hand_dye_scheme", {})
                                if pend_right_hand_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_right_hand_dye_scheme.scheme_index = pend_right_hand_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_right_hand_dye_scheme.is_un_lock = pend_right_hand_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_left_foot_dye_scheme
                                pend_left_foot_dye_scheme_data = outfit_preset_data.get("pend_left_foot_dye_scheme", {})
                                if pend_left_foot_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_left_foot_dye_scheme.scheme_index = pend_left_foot_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_left_foot_dye_scheme.is_un_lock = pend_left_foot_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_right_foot_dye_scheme
                                pend_right_foot_dye_scheme_data = outfit_preset_data.get("pend_right_foot_dye_scheme", {})
                                if pend_right_foot_dye_scheme_data:
                                    server_data_entry.player.team.char_2.outfit_preset.pend_right_foot_dye_scheme.scheme_index = pend_right_foot_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_2.outfit_preset.pend_right_foot_dye_scheme.is_un_lock = pend_right_foot_dye_scheme_data.get("is_un_lock", False)
                            
                            server_data_entry.player.team.char_2.gather_weapon = char_2_data.get("gather_weapon", 0)
                            
                            # Set character_appearance
                            character_appearance_data = char_2_data.get("character_appearance", {})
                            if character_appearance_data:
                                server_data_entry.player.team.char_2.character_appearance.badge = character_appearance_data.get("badge", 0)
                                server_data_entry.player.team.char_2.character_appearance.umbrella_id = character_appearance_data.get("umbrella_id", 0)
                                server_data_entry.player.team.char_2.character_appearance.insect_net_instance_id = character_appearance_data.get("insect_net_instance_id", 0)
                                server_data_entry.player.team.char_2.character_appearance.logging_axe_instance_id = character_appearance_data.get("logging_axe_instance_id", 0)
                                server_data_entry.player.team.char_2.character_appearance.water_bottle_instance_id = character_appearance_data.get("water_bottle_instance_id", 0)
                                server_data_entry.player.team.char_2.character_appearance.mining_hammer_instance_id = character_appearance_data.get("mining_hammer_instance_id", 0)
                                server_data_entry.player.team.char_2.character_appearance.collection_gloves_instance_id = character_appearance_data.get("collection_gloves_instance_id", 0)
                                server_data_entry.player.team.char_2.character_appearance.fishing_rod_instance_id = character_appearance_data.get("fishing_rod_instance_id", 0)
                            
                            # Set pos
                            pos_data = char_2_data.get("pos", {})
                            if pos_data:
                                server_data_entry.player.team.char_2.pos.x = pos_data.get("x", 0)
                                server_data_entry.player.team.char_2.pos.y = pos_data.get("y", 0)
                                server_data_entry.player.team.char_2.pos.z = pos_data.get("z", 0)
                                server_data_entry.player.team.char_2.pos.decimal_places = pos_data.get("decimal_places", 0)
                            
                            # Set rot
                            rot_data = char_2_data.get("rot", {})
                            if rot_data:
                                server_data_entry.player.team.char_2.rot.x = rot_data.get("x", 0)
                                server_data_entry.player.team.char_2.rot.y = rot_data.get("y", 0)
                                server_data_entry.player.team.char_2.rot.z = rot_data.get("z", 0)
                                server_data_entry.player.team.char_2.rot.decimal_places = rot_data.get("decimal_places", 0)
                            
                            server_data_entry.player.team.char_2.weapon_id = char_2_data.get("weapon_id", 0)
                            server_data_entry.player.team.char_2.weapon_star = char_2_data.get("weapon_star", 0)
                            server_data_entry.player.team.char_2.char_lv = char_2_data.get("char_lv", 0)
                            server_data_entry.player.team.char_2.char_star = char_2_data.get("char_star", 0)
                            server_data_entry.player.team.char_2.is_dead = char_2_data.get("is_dead", False)
                            server_data_entry.player.team.char_2.char_break_lv = char_2_data.get("char_break_lv", 0)
                            
                            # Set armors
                            for armor_data in char_2_data.get("armors", []):
                                armor = server_data_entry.player.team.char_2.armors.add()
                                armor.armor_id = armor_data.get("armor_id", 0)
                                armor.armor_star = armor_data.get("armor_star", 0)
                            
                            server_data_entry.player.team.char_2.inscription_id = char_2_data.get("inscription_id", 0)
                            server_data_entry.player.team.char_2.inscription_lv = char_2_data.get("inscription_lv", 0)
                            
                            # Set posters
                            for poster_data in char_2_data.get("posters", []):
                                poster = server_data_entry.player.team.char_2.posters.add()
                                poster.poster_id = poster_data.get("poster_id", 0)
                                poster.poster_star = poster_data.get("poster_star", 0)
                        
                        # Set char_3
                        char_3_data = team_data.get("char_3", {})
                        if char_3_data:
                            server_data_entry.player.team.char_3.char_id = char_3_data.get("char_id", 0)
                            
                            # Set outfit_preset
                            outfit_preset_data = char_3_data.get("outfit_preset", {})
                            if outfit_preset_data:
                                server_data_entry.player.team.char_3.outfit_preset.hat = outfit_preset_data.get("hat", 0)
                                server_data_entry.player.team.char_3.outfit_preset.hair = outfit_preset_data.get("hair", 0)
                                server_data_entry.player.team.char_3.outfit_preset.clothes = outfit_preset_data.get("clothes", 0)
                                server_data_entry.player.team.char_3.outfit_preset.ornament = outfit_preset_data.get("ornament", 0)
                                
                                # hat_dye_scheme
                                hat_dye_scheme_data = outfit_preset_data.get("hat_dye_scheme", {})
                                if hat_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.hat_dye_scheme.scheme_index = hat_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.hat_dye_scheme.is_un_lock = hat_dye_scheme_data.get("is_un_lock", False)
                                
                                # hair_dye_scheme
                                hair_dye_scheme_data = outfit_preset_data.get("hair_dye_scheme", {})
                                if hair_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.hair_dye_scheme.scheme_index = hair_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.hair_dye_scheme.is_un_lock = hair_dye_scheme_data.get("is_un_lock", False)
                                
                                # cloth_dye_scheme
                                cloth_dye_scheme_data = outfit_preset_data.get("cloth_dye_scheme", {})
                                if cloth_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.cloth_dye_scheme.scheme_index = cloth_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.cloth_dye_scheme.is_un_lock = cloth_dye_scheme_data.get("is_un_lock", False)
                                
                                # orn_dye_scheme
                                orn_dye_scheme_data = outfit_preset_data.get("orn_dye_scheme", {})
                                if orn_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.orn_dye_scheme.scheme_index = orn_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.orn_dye_scheme.is_un_lock = orn_dye_scheme_data.get("is_un_lock", False)
                                
                                # hide_info
                                hide_info_data = outfit_preset_data.get("hide_info", {})
                                if hide_info_data:
                                    server_data_entry.player.team.char_3.outfit_preset.hide_info.hide_orn = hide_info_data.get("hide_orn", False)
                                    server_data_entry.player.team.char_3.outfit_preset.hide_info.hide_braid = hide_info_data.get("hide_braid", False)
                                
                                server_data_entry.player.team.char_3.outfit_preset.pend_top = outfit_preset_data.get("pend_top", 0)
                                server_data_entry.player.team.char_3.outfit_preset.pend_chest = outfit_preset_data.get("pend_chest", 0)
                                server_data_entry.player.team.char_3.outfit_preset.pend_pelvis = outfit_preset_data.get("pend_pelvis", 0)
                                server_data_entry.player.team.char_3.outfit_preset.pend_up_face = outfit_preset_data.get("pend_up_face", 0)
                                server_data_entry.player.team.char_3.outfit_preset.pend_down_face = outfit_preset_data.get("pend_down_face", 0)
                                server_data_entry.player.team.char_3.outfit_preset.pend_left_hand = outfit_preset_data.get("pend_left_hand", 0)
                                server_data_entry.player.team.char_3.outfit_preset.pend_right_hand = outfit_preset_data.get("pend_right_hand", 0)
                                server_data_entry.player.team.char_3.outfit_preset.pend_left_foot = outfit_preset_data.get("pend_left_foot", 0)
                                server_data_entry.player.team.char_3.outfit_preset.pend_right_foot = outfit_preset_data.get("pend_right_foot", 0)
                                
                                # pend_top_dye_scheme
                                pend_top_dye_scheme_data = outfit_preset_data.get("pend_top_dye_scheme", {})
                                if pend_top_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_top_dye_scheme.scheme_index = pend_top_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_top_dye_scheme.is_un_lock = pend_top_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_chest_dye_scheme
                                pend_chest_dye_scheme_data = outfit_preset_data.get("pend_chest_dye_scheme", {})
                                if pend_chest_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_chest_dye_scheme.scheme_index = pend_chest_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_chest_dye_scheme.is_un_lock = pend_chest_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_pelvis_dye_scheme
                                pend_pelvis_dye_scheme_data = outfit_preset_data.get("pend_pelvis_dye_scheme", {})
                                if pend_pelvis_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_pelvis_dye_scheme.scheme_index = pend_pelvis_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_pelvis_dye_scheme.is_un_lock = pend_pelvis_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_up_face_dye_scheme
                                pend_up_face_dye_scheme_data = outfit_preset_data.get("pend_up_face_dye_scheme", {})
                                if pend_up_face_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_up_face_dye_scheme.scheme_index = pend_up_face_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_up_face_dye_scheme.is_un_lock = pend_up_face_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_down_face_dye_scheme
                                pend_down_face_dye_scheme_data = outfit_preset_data.get("pend_down_face_dye_scheme", {})
                                if pend_down_face_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_down_face_dye_scheme.scheme_index = pend_down_face_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_down_face_dye_scheme.is_un_lock = pend_down_face_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_left_hand_dye_scheme
                                pend_left_hand_dye_scheme_data = outfit_preset_data.get("pend_left_hand_dye_scheme", {})
                                if pend_left_hand_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_left_hand_dye_scheme.scheme_index = pend_left_hand_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_left_hand_dye_scheme.is_un_lock = pend_left_hand_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_right_hand_dye_scheme
                                pend_right_hand_dye_scheme_data = outfit_preset_data.get("pend_right_hand_dye_scheme", {})
                                if pend_right_hand_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_right_hand_dye_scheme.scheme_index = pend_right_hand_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_right_hand_dye_scheme.is_un_lock = pend_right_hand_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_left_foot_dye_scheme
                                pend_left_foot_dye_scheme_data = outfit_preset_data.get("pend_left_foot_dye_scheme", {})
                                if pend_left_foot_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_left_foot_dye_scheme.scheme_index = pend_left_foot_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_left_foot_dye_scheme.is_un_lock = pend_left_foot_dye_scheme_data.get("is_un_lock", False)
                                
                                # pend_right_foot_dye_scheme
                                pend_right_foot_dye_scheme_data = outfit_preset_data.get("pend_right_foot_dye_scheme", {})
                                if pend_right_foot_dye_scheme_data:
                                    server_data_entry.player.team.char_3.outfit_preset.pend_right_foot_dye_scheme.scheme_index = pend_right_foot_dye_scheme_data.get("scheme_index", 0)
                                    server_data_entry.player.team.char_3.outfit_preset.pend_right_foot_dye_scheme.is_un_lock = pend_right_foot_dye_scheme_data.get("is_un_lock", False)
                            
                            server_data_entry.player.team.char_3.gather_weapon = char_3_data.get("gather_weapon", 0)
                            
                            # Set character_appearance
                            character_appearance_data = char_3_data.get("character_appearance", {})
                            if character_appearance_data:
                                server_data_entry.player.team.char_3.character_appearance.badge = character_appearance_data.get("badge", 0)
                                server_data_entry.player.team.char_3.character_appearance.umbrella_id = character_appearance_data.get("umbrella_id", 0)
                                server_data_entry.player.team.char_3.character_appearance.insect_net_instance_id = character_appearance_data.get("insect_net_instance_id", 0)
                                server_data_entry.player.team.char_3.character_appearance.logging_axe_instance_id = character_appearance_data.get("logging_axe_instance_id", 0)
                                server_data_entry.player.team.char_3.character_appearance.water_bottle_instance_id = character_appearance_data.get("water_bottle_instance_id", 0)
                                server_data_entry.player.team.char_3.character_appearance.mining_hammer_instance_id = character_appearance_data.get("mining_hammer_instance_id", 0)
                                server_data_entry.player.team.char_3.character_appearance.collection_gloves_instance_id = character_appearance_data.get("collection_gloves_instance_id", 0)
                                server_data_entry.player.team.char_3.character_appearance.fishing_rod_instance_id = character_appearance_data.get("fishing_rod_instance_id", 0)
                            
                            # Set pos
                            pos_data = char_3_data.get("pos", {})
                            if pos_data:
                                server_data_entry.player.team.char_3.pos.x = pos_data.get("x", 0)
                                server_data_entry.player.team.char_3.pos.y = pos_data.get("y", 0)
                                server_data_entry.player.team.char_3.pos.z = pos_data.get("z", 0)
                                server_data_entry.player.team.char_3.pos.decimal_places = pos_data.get("decimal_places", 0)
                            
                            # Set rot
                            rot_data = char_3_data.get("rot", {})
                            if rot_data:
                                server_data_entry.player.team.char_3.rot.x = rot_data.get("x", 0)
                                server_data_entry.player.team.char_3.rot.y = rot_data.get("y", 0)
                                server_data_entry.player.team.char_3.rot.z = rot_data.get("z", 0)
                                server_data_entry.player.team.char_3.rot.decimal_places = rot_data.get("decimal_places", 0)
                            
                            server_data_entry.player.team.char_3.weapon_id = char_3_data.get("weapon_id", 0)
                            server_data_entry.player.team.char_3.weapon_star = char_3_data.get("weapon_star", 0)
                            server_data_entry.player.team.char_3.char_lv = char_3_data.get("char_lv", 0)
                            server_data_entry.player.team.char_3.char_star = char_3_data.get("char_star", 0)
                            server_data_entry.player.team.char_3.is_dead = char_3_data.get("is_dead", False)
                            server_data_entry.player.team.char_3.char_break_lv = char_3_data.get("char_break_lv", 0)
                            
                            # Set armors
                            for armor_data in char_3_data.get("armors", []):
                                armor = server_data_entry.player.team.char_3.armors.add()
                                armor.armor_id = armor_data.get("armor_id", 0)
                                armor.armor_star = armor_data.get("armor_star", 0)
                            
                            server_data_entry.player.team.char_3.inscription_id = char_3_data.get("inscription_id", 0)
                            server_data_entry.player.team.char_3.inscription_lv = char_3_data.get("inscription_lv", 0)
                            
                            # Set posters
                            for poster_data in char_3_data.get("posters", []):
                                poster = server_data_entry.player.team.char_3.posters.add()
                                poster.poster_id = poster_data.get("poster_id", 0)
                                poster.poster_star = poster_data.get("poster_star", 0)
                
                server_data_entry.tod_time = server_data_obj.get("tod_time", 0)
                
                # Set character
                character_data = server_data_obj.get("character", {})
                if character_data:
                    server_data_entry.character.character_id = character_data.get("character_id", 0)
                    
                    # Set outfit_preset
                    outfit_preset_data = character_data.get("outfit_preset", {})
                    if outfit_preset_data:
                        server_data_entry.character.outfit_preset.hat = outfit_preset_data.get("hat", 0)
                        server_data_entry.character.outfit_preset.hair = outfit_preset_data.get("hair", 0)
                        server_data_entry.character.outfit_preset.clothes = outfit_preset_data.get("clothes", 0)
                        server_data_entry.character.outfit_preset.ornament = outfit_preset_data.get("ornament", 0)
                        
                        # hat_dye_scheme
                        hat_dye_scheme_data = outfit_preset_data.get("hat_dye_scheme", {})
                        if hat_dye_scheme_data:
                            server_data_entry.character.outfit_preset.hat_dye_scheme.scheme_index = hat_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.hat_dye_scheme.is_un_lock = hat_dye_scheme_data.get("is_un_lock", False)
                        
                        # hair_dye_scheme
                        hair_dye_scheme_data = outfit_preset_data.get("hair_dye_scheme", {})
                        if hair_dye_scheme_data:
                            server_data_entry.character.outfit_preset.hair_dye_scheme.scheme_index = hair_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.hair_dye_scheme.is_un_lock = hair_dye_scheme_data.get("is_un_lock", False)
                        
                        # cloth_dye_scheme
                        cloth_dye_scheme_data = outfit_preset_data.get("cloth_dye_scheme", {})
                        if cloth_dye_scheme_data:
                            server_data_entry.character.outfit_preset.cloth_dye_scheme.scheme_index = cloth_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.cloth_dye_scheme.is_un_lock = cloth_dye_scheme_data.get("is_un_lock", False)
                        
                        # orn_dye_scheme
                        orn_dye_scheme_data = outfit_preset_data.get("orn_dye_scheme", {})
                        if orn_dye_scheme_data:
                            server_data_entry.character.outfit_preset.orn_dye_scheme.scheme_index = orn_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.orn_dye_scheme.is_un_lock = orn_dye_scheme_data.get("is_un_lock", False)
                        
                        # hide_info
                        hide_info_data = outfit_preset_data.get("hide_info", {})
                        if hide_info_data:
                            server_data_entry.character.outfit_preset.hide_info.hide_orn = hide_info_data.get("hide_orn", False)
                            server_data_entry.character.outfit_preset.hide_info.hide_braid = hide_info_data.get("hide_braid", False)
                        
                        server_data_entry.character.outfit_preset.pend_top = outfit_preset_data.get("pend_top", 0)
                        server_data_entry.character.outfit_preset.pend_chest = outfit_preset_data.get("pend_chest", 0)
                        server_data_entry.character.outfit_preset.pend_pelvis = outfit_preset_data.get("pend_pelvis", 0)
                        server_data_entry.character.outfit_preset.pend_up_face = outfit_preset_data.get("pend_up_face", 0)
                        server_data_entry.character.outfit_preset.pend_down_face = outfit_preset_data.get("pend_down_face", 0)
                        server_data_entry.character.outfit_preset.pend_left_hand = outfit_preset_data.get("pend_left_hand", 0)
                        server_data_entry.character.outfit_preset.pend_right_hand = outfit_preset_data.get("pend_right_hand", 0)
                        server_data_entry.character.outfit_preset.pend_left_foot = outfit_preset_data.get("pend_left_foot", 0)
                        server_data_entry.character.outfit_preset.pend_right_foot = outfit_preset_data.get("pend_right_foot", 0)
                        
                        # pend_top_dye_scheme
                        pend_top_dye_scheme_data = outfit_preset_data.get("pend_top_dye_scheme", {})
                        if pend_top_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_top_dye_scheme.scheme_index = pend_top_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_top_dye_scheme.is_un_lock = pend_top_dye_scheme_data.get("is_un_lock", False)
                        
                        # pend_chest_dye_scheme
                        pend_chest_dye_scheme_data = outfit_preset_data.get("pend_chest_dye_scheme", {})
                        if pend_chest_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_chest_dye_scheme.scheme_index = pend_chest_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_chest_dye_scheme.is_un_lock = pend_chest_dye_scheme_data.get("is_un_lock", False)
                        
                        # pend_pelvis_dye_scheme
                        pend_pelvis_dye_scheme_data = outfit_preset_data.get("pend_pelvis_dye_scheme", {})
                        if pend_pelvis_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_pelvis_dye_scheme.scheme_index = pend_pelvis_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_pelvis_dye_scheme.is_un_lock = pend_pelvis_dye_scheme_data.get("is_un_lock", False)
                        
                        # pend_up_face_dye_scheme
                        pend_up_face_dye_scheme_data = outfit_preset_data.get("pend_up_face_dye_scheme", {})
                        if pend_up_face_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_up_face_dye_scheme.scheme_index = pend_up_face_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_up_face_dye_scheme.is_un_lock = pend_up_face_dye_scheme_data.get("is_un_lock", False)
                        
                        # pend_down_face_dye_scheme
                        pend_down_face_dye_scheme_data = outfit_preset_data.get("pend_down_face_dye_scheme", {})
                        if pend_down_face_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_down_face_dye_scheme.scheme_index = pend_down_face_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_down_face_dye_scheme.is_un_lock = pend_down_face_dye_scheme_data.get("is_un_lock", False)
                        
                        # pend_left_hand_dye_scheme
                        pend_left_hand_dye_scheme_data = outfit_preset_data.get("pend_left_hand_dye_scheme", {})
                        if pend_left_hand_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_left_hand_dye_scheme.scheme_index = pend_left_hand_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_left_hand_dye_scheme.is_un_lock = pend_left_hand_dye_scheme_data.get("is_un_lock", False)
                        
                        # pend_right_hand_dye_scheme
                        pend_right_hand_dye_scheme_data = outfit_preset_data.get("pend_right_hand_dye_scheme", {})
                        if pend_right_hand_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_right_hand_dye_scheme.scheme_index = pend_right_hand_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_right_hand_dye_scheme.is_un_lock = pend_right_hand_dye_scheme_data.get("is_un_lock", False)
                        
                        # pend_left_foot_dye_scheme
                        pend_left_foot_dye_scheme_data = outfit_preset_data.get("pend_left_foot_dye_scheme", {})
                        if pend_left_foot_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_left_foot_dye_scheme.scheme_index = pend_left_foot_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_left_foot_dye_scheme.is_un_lock = pend_left_foot_dye_scheme_data.get("is_un_lock", False)
                        
                        # pend_right_foot_dye_scheme
                        pend_right_foot_dye_scheme_data = outfit_preset_data.get("pend_right_foot_dye_scheme", {})
                        if pend_right_foot_dye_scheme_data:
                            server_data_entry.character.outfit_preset.pend_right_foot_dye_scheme.scheme_index = pend_right_foot_dye_scheme_data.get("scheme_index", 0)
                            server_data_entry.character.outfit_preset.pend_right_foot_dye_scheme.is_un_lock = pend_right_foot_dye_scheme_data.get("is_un_lock", False)
                    
                    server_data_entry.character.furniture_id = character_data.get("furniture_id", 0)
                    server_data_entry.character.seat_id = character_data.get("seat_id", 0)
        
        # Send response
        session.send(CmdId.ServerSceneSyncDataNotice, rsp, False, packet_id)