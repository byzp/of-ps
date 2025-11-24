from re import T
import proto.OverField_pb2 as pb
import utils.db as db
from datetime import datetime


def make_ScenePlayer(session):
    # 构造ScenePlayer
    player = session.scene_player
    player.player_id = session.player_id
    player.player_name = session.player_name

    player.food_buff_ids.extend([5013073])  # 食物buff ID
    player.global_buff_ids.extend([481, 491])  # 全局buff ID buff未实现

    birthday_str = db.get_players_info(session.player_id, "birthday")
    if birthday_str:
        birthday_date = datetime.strptime(birthday_str, "%Y-%m-%d")
        today = datetime.now()
        player.is_birthday = (
            today.month == birthday_date.month and today.day == birthday_date.day
        )
    else:
        player.is_birthday = False  # 判断生日

    char_ids = db.get_players_info(session.player_id, "team")
    if char_ids[0]:
        char_1 = player.team.char_1
        char_1.char_id = char_ids[0]

        chr = pb.Character()
        chr.ParseFromString(db.get_characters(session.player_id, char_ids[0])[0])
        char_1.outfit_preset.ParseFromString(
            make_SceneCharacterOutfitPreset(
                session, chr.outfit_presets[chr.in_use_outfit_preset_index]
            )
        )

        char_1.character_appearance.CopyFrom(chr.character_appearance)
        char_1.char_lv = chr.level
        char_1.char_star = chr.star
        char_1.char_break_lv = chr.max_level
        char_1.weapon_id = chr.equipment_presets[0].weapon
        char_1.gather_weapon = chr.gather_weapon  # 设置采集武器
        # TODO: 铭文id 铭文等级 防具列表 映像列表

        # char_1.pos.CopyFrom(pb.Vector3())
        # char_1.rot.CopyFrom(pb.Vector3())
        char_1.pos.x = 2394
        char_1.pos.y = 908
        char_1.rot.CopyFrom(pb.Vector3())
    if char_ids[1]:
        char_2 = player.team.char_2
        char_2.char_id = char_ids[1]

        chr = pb.Character()
        chr.ParseFromString(db.get_characters(session.player_id, char_ids[1])[0])
        char_2.outfit_preset.ParseFromString(
            make_SceneCharacterOutfitPreset(
                session, chr.outfit_presets[chr.in_use_outfit_preset_index]
            )
        )

        char_2.character_appearance.CopyFrom(chr.character_appearance)
        char_2.char_lv = chr.level
        char_2.char_star = chr.star
        char_2.char_break_lv = chr.max_level
        # 从equipment_presets中获取武器ID
        char_2.weapon_id = chr.equipment_presets[0].weapon
        char_2.gather_weapon = chr.gather_weapon  # 设置采集武器
        # TODO: 铭文id 铭文等级 防具列表 映像列表

        char_2.pos.x = 2394
        char_2.pos.y = 908
        char_2.rot.CopyFrom(pb.Vector3())
    if char_ids[2]:
        char_3 = player.team.char_3
        char_3.char_id = char_ids[2]

        chr = pb.Character()
        chr.ParseFromString(db.get_characters(session.player_id, char_ids[2])[0])
        char_3.outfit_preset.ParseFromString(
            make_SceneCharacterOutfitPreset(
                session, chr.outfit_presets[chr.in_use_outfit_preset_index]
            )
        )

        char_3.character_appearance.CopyFrom(chr.character_appearance)
        char_3.char_lv = chr.level
        char_3.char_star = chr.star
        char_3.char_break_lv = chr.max_level
        # 从equipment_presets中获取武器ID
        char_3.weapon_id = chr.equipment_presets[0].weapon
        char_3.gather_weapon = chr.gather_weapon  # 设置采集武器
        # TODO: 铭文id 铭文等级 防具列表 映像列表

        char_3.pos.x = 2394
        char_3.pos.y = 908
        char_3.rot.CopyFrom(pb.Vector3())


def make_SceneCharacterOutfitPreset(session, outfit):
    sc = pb.SceneCharacterOutfitPreset()
    item = pb.ItemDetail()
    if outfit.hat > 0:
        item.ParseFromString(db.get_item_detail(session.player_id, outfit.hat))
        sc.hat = outfit.hat
        sc.hat_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.hat_dye_scheme_index]
        )
    if outfit.hair > 0:
        item.ParseFromString(db.get_item_detail(session.player_id, outfit.hair))
        sc.hair = outfit.hair
        sc.hair_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.hair_dye_scheme_index]
        )
    if outfit.clothes > 0:
        item.ParseFromString(db.get_item_detail(session.player_id, outfit.clothes))
        sc.clothes = outfit.clothes
        sc.cloth_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.clothes_dye_scheme_index]
        )
    if outfit.ornament > 0:
        item.ParseFromString(db.get_item_detail(session.player_id, outfit.ornament))
        sc.ornament = outfit.ornament
        sc.orn_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.ornament_dye_scheme_index]
        )

    sc.hide_info.CopyFrom(outfit.outfit_hide_info)

    if outfit.pend_top > 0:
        item.ParseFromString(db.get_item_detail(session.player_id, outfit.pend_top))
        sc.pend_top = outfit.pend_top
        sc.pend_top_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_top_dye_scheme_index]
        )
    if outfit.pend_chest > 0:
        item.ParseFromString(db.get_item_detail(session.player_id, outfit.pend_chest))
        sc.pend_chest = outfit.pend_chest
        sc.pend_chest_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_chest_dye_scheme_index]
        )
    if outfit.pend_pelvis > 0:
        item.ParseFromString(db.get_item_detail(session.player_id, outfit.pend_pelvis))
        sc.pend_pelvis = outfit.pend_pelvis
        sc.pend_pelvis_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_pelvis_dye_scheme_index]
        )
    if outfit.pend_up_face > 0:
        item.ParseFromString(db.get_item_detail(session.player_id, outfit.pend_up_face))
        sc.pend_up_face = outfit.pend_up_face
        sc.pend_up_face_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_up_face_dye_scheme_index]
        )
    if outfit.pend_down_face > 0:
        item.ParseFromString(
            db.get_item_detail(session.player_id, outfit.pend_down_face)
        )
        sc.pend_down_face = outfit.pend_down_face
        sc.pend_down_face_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_down_face_dye_scheme_index]
        )
    if outfit.pend_left_hand > 0:
        item.ParseFromString(
            db.get_item_detail(session.player_id, outfit.pend_left_hand)
        )
        sc.pend_left_hand = outfit.pend_left_hand
        sc.pend_left_hand_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_left_hand_dye_scheme_index]
        )
    if outfit.pend_right_hand > 0:
        item.ParseFromString(
            db.get_item_detail(session.player_id, outfit.pend_right_hand)
        )
        sc.pend_right_hand = outfit.pend_right_hand
        sc.pend_right_hand_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_right_hand_dye_scheme_index]
        )
    if outfit.pend_left_foot > 0:
        item.ParseFromString(
            db.get_item_detail(session.player_id, outfit.pend_left_foot)
        )
        sc.pend_left_foot = outfit.pend_left_foot
        sc.pend_left_foot_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_left_foot_dye_scheme_index]
        )
    if outfit.pend_right_foot > 0:
        item.ParseFromString(
            db.get_item_detail(session.player_id, outfit.pend_right_foot)
        )
        sc.pend_right_foot = outfit.pend_right_foot
        sc.pend_right_foot_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_right_foot_dye_scheme_index]
        )

    return sc.SerializeToString()
