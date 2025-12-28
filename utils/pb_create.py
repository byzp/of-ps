import proto.OverField_pb2 as pb
import utils.db as db
from datetime import datetime
from utils.res_loader import res
import random
import server.scene_data as scene_data
import server.notice_sync as notice_sync


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
    player.team.CopyFrom(make_SceneTeam(session.player_id, char_ids))


def make_SceneTeam(player_id, char_ids):
    team = pb.SceneTeam()
    if char_ids[0]:
        char1 = team.char1
        char1.char_id = char_ids[0]

        chr = pb.Character()
        chr.ParseFromString(db.get_characters(player_id, char_ids[0])[0])
        char1.outfit_preset.CopyFrom(
            make_SceneCharacterOutfitPreset(
                player_id, chr.outfit_presets[chr.in_use_outfit_preset_index]
            )
        )

        char1.character_appearance.CopyFrom(chr.character_appearance)
        char1.char_lv = chr.level
        char1.char_star = chr.star
        char1.char_break_lv = chr.max_level
        char1.weapon_id = chr.equipment_presets[0].weapon
        char1.gather_weapon = chr.gather_weapon  # 设置采集武器
        # TODO: 铭文id 铭文等级 防具列表 映像列表

        # char1.pos.CopyFrom(pb.Vector3())
        # char1.rot.CopyFrom(pb.Vector3())
        char1.pos.x = 2394
        char1.pos.y = 908
        char1.rot.CopyFrom(pb.Vector3())
    if char_ids[1]:
        char2 = team.char2
        char2.char_id = char_ids[1]

        chr = pb.Character()
        chr.ParseFromString(db.get_characters(player_id, char_ids[1])[0])
        char2.outfit_preset.CopyFrom(
            make_SceneCharacterOutfitPreset(
                player_id, chr.outfit_presets[chr.in_use_outfit_preset_index]
            )
        )

        char2.character_appearance.CopyFrom(chr.character_appearance)
        char2.char_lv = chr.level
        char2.char_star = chr.star
        char2.char_break_lv = chr.max_level
        # 从equipment_presets中获取武器ID
        char2.weapon_id = chr.equipment_presets[0].weapon
        char2.gather_weapon = chr.gather_weapon  # 设置采集武器
        # TODO: 铭文id 铭文等级 防具列表 映像列表

        char2.pos.x = 2394
        char2.pos.y = 908
        char2.rot.CopyFrom(pb.Vector3())
    if char_ids[2]:
        char3 = team.char3
        char3.char_id = char_ids[2]

        chr = pb.Character()
        chr.ParseFromString(db.get_characters(player_id, char_ids[2])[0])
        char3.outfit_preset.CopyFrom(
            make_SceneCharacterOutfitPreset(
                player_id, chr.outfit_presets[chr.in_use_outfit_preset_index]
            )
        )

        char3.character_appearance.CopyFrom(chr.character_appearance)
        char3.char_lv = chr.level
        char3.char_star = chr.star
        char3.char_break_lv = chr.max_level
        # 从equipment_presets中获取武器ID
        char3.weapon_id = chr.equipment_presets[0].weapon
        char3.gather_weapon = chr.gather_weapon  # 设置采集武器
        # TODO: 铭文id 铭文等级 防具列表 映像列表

        char3.pos.x = 2394
        char3.pos.y = 908
        char3.rot.CopyFrom(pb.Vector3())
    return team


def make_SceneCharacterOutfitPreset(player_id, outfit):
    sc = pb.SceneCharacterOutfitPreset()
    item = pb.ItemDetail()
    if outfit.hat > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.hat))
        sc.hat = outfit.hat
        sc.hat_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.hat_dye_scheme_index]
        )
    if outfit.hair > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.hair))
        sc.hair = outfit.hair
        sc.hair_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.hair_dye_scheme_index]
        )
    if outfit.clothes > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.clothes))
        sc.clothes = outfit.clothes
        sc.cloth_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.clothes_dye_scheme_index]
        )
    if outfit.ornament > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.ornament))
        sc.ornament = outfit.ornament
        sc.orn_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.ornament_dye_scheme_index]
        )

    sc.hide_info.CopyFrom(outfit.outfit_hide_info)

    if outfit.pend_top > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_top))
        sc.pend_top = outfit.pend_top
        sc.pend_top_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_top_dye_scheme_index]
        )
    if outfit.pend_chest > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_chest))
        sc.pend_chest = outfit.pend_chest
        sc.pend_chest_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_chest_dye_scheme_index]
        )
    if outfit.pend_pelvis > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_pelvis))
        sc.pend_pelvis = outfit.pend_pelvis
        sc.pend_pelvis_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_pelvis_dye_scheme_index]
        )
    if outfit.pend_up_face > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_up_face))
        sc.pend_up_face = outfit.pend_up_face
        sc.pend_up_face_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_up_face_dye_scheme_index]
        )
    if outfit.pend_down_face > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_down_face))
        sc.pend_down_face = outfit.pend_down_face
        sc.pend_down_face_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_down_face_dye_scheme_index]
        )
    if outfit.pend_left_hand > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_left_hand))
        sc.pend_left_hand = outfit.pend_left_hand
        sc.pend_left_hand_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_left_hand_dye_scheme_index]
        )
    if outfit.pend_right_hand > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_right_hand))
        sc.pend_right_hand = outfit.pend_right_hand
        sc.pend_right_hand_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_right_hand_dye_scheme_index]
        )
    if outfit.pend_left_foot > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_left_foot))
        sc.pend_left_foot = outfit.pend_left_foot
        sc.pend_left_foot_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_left_foot_dye_scheme_index]
        )
    if outfit.pend_right_foot > 0:
        item.ParseFromString(db.get_item_detail(player_id, outfit.pend_right_foot))
        sc.pend_right_foot = outfit.pend_right_foot
        sc.pend_right_foot_dye_scheme.CopyFrom(
            item.main_item.outfit.dye_schemes[outfit.pend_right_foot_dye_scheme_index]
        )

    return sc


def make_item(item_id, num=1, player_id=0) -> list:
    for i in res["Item"]["item"]["datas"]:
        if i["i_d"] == item_id:
            items = None
            match i["new_bag_item_tag"]:
                case pb.EBagItemTag_Gift:  # 礼包 tag:1
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Weapon:  # 武器 tag:2
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    weapon = tmp.weapon
                    weapon.weapon_id = i["i_d"]
                    weapon.instance_id = db.get_instance_id(player_id)
                    weapon.attack = 35
                    weapon.damage_balance = 0
                    weapon.critical_ratio = 0
                    weapon.level = 1
                    weapon.star = 1
                    weapon.property_index = 1

                    # 将武器数据序列化并更新到 items 数据库
                case pb.EBagItemTag_Armor:  # 防具 tag:3
                    # # 1100=0, 1200=2, 1300=5, 1400=7, 1500=8
                    # armor_property_mapping = {1100: 0, 1200: 2, 1300: 5, 1400: 7, 1500: 8}

                    # # 查找对应的 armor 数据
                    # armor_data = None
                    # for armor_item in res["Armor"]["armor"]["datas"]:
                    #     if armor_item["i_d"] == i["i_d"]:
                    #         armor_data = armor_item
                    #         break

                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.is_new = False
                    tmp.temp_pack_index = 0
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1
                    armor = tmp.armor
                    armor.armor_id = i["i_d"]
                    armor.instance_id = db.get_instance_id(player_id)
                    armor.main_property_type = pb.EPropertyType_DamageBalance
                    # if armor_data:
                    #     armor.main_property_type = armor_property_mapping.get(
                    #         armor_data["armor_property_i_d"]
                    #     )  # 主属性还是有问题
                    armor.main_property_val = 10000
                    armor.wearer_id = 0
                    armor.level = 100
                    armor.strength_level = 5
                    armor.strength_exp = 0
                    armor.property_index = 0
                    armor.is_lock = False

                    # 将护甲数据序列化并更新到 items 数据库
                case pb.EBagItemTag_Fragment:  # 角色碎片 tag:4
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Poster:  # 映像 tag:5
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    poster = tmp.poster
                    poster.poster_id = i["i_d"]
                    poster.instance_id = db.get_instance_id(player_id)
                    poster.star = 5

                    # 将海报数据序列化并更新到 items 数据库
                case pb.EBagItemTag_Collection:  # 收藏品 tag:6
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Card:  # 收藏卡 tag:7
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.character.character_id = i["i_d"]
                    # 这个好像是多余的角色碎片转换成星辰后，删除角色碎片的通知

                case pb.EBagItemTag_Material:  # 材料 tag:8
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Currency:  # 货币 tag:9
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Food:  # 食物 tag:10
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Item:  # 普通道具 tag:12
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Fish:  # 鱼产 tag:13
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Baitbox:  # 鱼饵箱 tag:15
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Inscription:  # 铭文 tag:17
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.inscription.inscription_id = i["i_d"]
                    tmp.inscription.level = 5

                case pb.EBagItemTag_StrengthStone:  # 强化石 tag:18
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_ExpBook:  # 经验书 能量饮料 tag:19
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Head:  # 头像 tag:20
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1

                case pb.EBagItemTag_Fashion:  # 时装 tag:21
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    outfit = tmp.outfit
                    outfit.outfit_id = i["i_d"]
                    dye_scheme = outfit.dye_schemes.add()
                    dye_scheme.is_un_lock = True

                case pb.EBagItemTag_UnlockItem:  # 解锁道具 tag:22
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 2  # 1/2

                case pb.EBagItemTag_AbilityItem:  # 能力道具 tag:23
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_UnlockAbilityItem:  # 解锁能力道具 tag:24
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1

                case pb.EBagItemTag_CharacterBadge:  # 角色徽章 tag:25
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 8

                case pb.EBagItemTag_DyeStuff:  # 染料 tag:26
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Agentia:  # 特殊道具 女装之魂 蔷薇之心 等 tag:29
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_MoonStone:  # 月石 技能材料 tag:30
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Umbrella:  # 伞 tag:31
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1

                case pb.EBagItemTag_Vitality:  # 体力药剂 tag:32
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Badge:  # 头衔 tag:33
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1

                case pb.EBagItemTag_Furniture:  # 家具 tag:34
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_Energy:  # 精力药水 tag:35
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_TeleportKey:  # 采集空间钥匙 tag:38
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_WallPaper:  # 壁纸 tag:39
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1

                case pb.EBagItemTag_Expression:  # 表情 tag:40
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1
                    item_detail.extra_quality = i["quality"]

                case pb.EBagItemTag_MoonCard:  # 月卡通知也许 未发现实际内容 tag:41
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num
                    item_detail.extra_quality = i["quality"]

                case pb.EBagItemTag_PhoneCase:  # 手机壁纸 tag:42
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1

                case pb.EBagItemTag_Pendant:  # 挂件 tag:43
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1

                case pb.EBagItemTag_AvatarFrame:  # 头像框 tag:44
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = 1

                case pb.EBagItemTag_IntimacyGift:  # 亲密度礼物 tag:45
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_MusicNote:  # 音乐册 tag:46
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_MonthlyCard:  # 月度卡 未知 tag:47
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_BattlePassCard:  # 战斗通行证 未知 tag:48
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_MonthlyGiftCard:  # 月度礼物卡 tag:49
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_BattlePassGiftCard:  # 战斗通行证礼物卡 tag:50
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num

                case pb.EBagItemTag_SeasonalMiniGamesItem:  # 小游戏道具 tag:51
                    item_detail = pb.ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num
            return item_detail


def make_treasure_box_item(
    player_id,
    world_level,
    num=0,
) -> list:  # TODO 仅生成武器和防具, 未考虑未解锁的武器, 未实现根据世界等级调整概率,
    if not num:
        num = random.randint(2, 7)
    wp_num = random.randint(0, num)
    armor_num = num - wp_num
    items = []
    wp_len = len(res["Weapon"]["weapon"]["datas"])
    while wp_num > 0:
        weapon_i = res["Weapon"]["weapon"]["datas"][random.randint(0, wp_len - 1)]
        item_detail = pb.ItemDetail()
        item_detail.pack_type = pb.ItemDetail.PackType.PackType_TempStorageArea
        tmp = item_detail.main_item
        if not weapon_i.get("item_i_d"):
            continue
        tmp.item_id = weapon_i["item_i_d"]
        tmp.item_tag = pb.EBagItemTag_Weapon
        weapon = tmp.weapon
        weapon.weapon_id = weapon_i["item_i_d"]
        weapon.instance_id = db.get_instance_id(player_id)
        for prop in res["Weapon"]["weapon_property"]["datas"]:
            if weapon_i["weapon_property_i_d"] == prop["i_d"]:
                weapon.property_index = random.randint(
                    1, len(prop["weapon_property_group_info"])
                )
                group_s = prop["weapon_property_group_info"][weapon.property_index - 1]
                if not group_s.get("min_attack"):
                    continue
                weapon.attack = int(
                    random.uniform(group_s["min_attack"], group_s["max_attack"])
                )
                weapon.damage_balance = int(
                    random.uniform(
                        group_s["min_damage_balance"], group_s["max_damage_balance"]
                    )
                )
                weapon.critical_ratio = int(
                    random.uniform(
                        group_s["min_critical_ratio"], group_s["max_critical_ratio"]
                    )
                )
                weapon.level = random.randint(
                    group_s["min_level"], group_s["max_level"]
                )
                weapon.star = 1
                items.append(item_detail)
                wp_num -= 1
                break
    armor_len = len(res["Armor"]["armor"]["datas"])
    while armor_num > 0:
        armor_i = res["Armor"]["armor"]["datas"][random.randint(0, armor_len - 1)]
        item_detail = pb.ItemDetail()
        tmp = item_detail.main_item
        tmp.item_id = armor_i["i_d"]
        tmp.item_tag = pb.EBagItemTag_Armor
        # tmp.is_new = False
        armor = tmp.armor
        armor.armor_id = armor_i["i_d"]
        armor.instance_id = db.get_instance_id(player_id)
        for prop in res["Armor"]["armor_property"]["datas"]:
            if armor_i["armor_property_i_d"] == prop["i_d"]:
                armor.property_index = random.randint(
                    1, len(prop["armor_property_group_info"])
                )
                group_s = prop["armor_property_group_info"][armor.property_index - 1]
                prop_group = {
                    pb.EPropertyType_ExtHp: ["min_ext_hp", "max_ext_hp"],
                    pb.EPropertyType_MaxHPPercent: ["min_hp_percent", "max_hp_percent"],
                    pb.EPropertyType_ExtAttack: ["min_ext_attack", "max_ext_attack"],
                    pb.EPropertyType_AttackPercent: [
                        "min_attack_percent",
                        "max_attack_percent",
                    ],
                    pb.EPropertyType_ExtDefense: ["min_ext_defense", "max_ext_defense"],
                    pb.EPropertyType_DefensePercent: [
                        "min_defense_percent",
                        "max_defense_percent",
                    ],
                    pb.EPropertyType_CriticalRatio: [
                        "min_critical_ratio",
                        "max_critical_ratio",
                    ],
                    pb.EPropertyType_CriticalDamagePercent: [
                        "min_critical_damage_percent",
                        "max_critical_damage_percent",
                    ],
                    pb.EPropertyType_RecoverPercent: [
                        "min_recover_percent",
                        "max_recover_percent",
                    ],
                }
                armor.main_property_type = random.choice(list(prop_group.keys()))
                armor.main_property_val = 0
                random.uniform(
                    group_s[prop_group[armor.main_property_type][0]],
                    group_s[prop_group[armor.main_property_type][1]],
                )
                armor.wearer_id = 0
                armor.level = random.randint(group_s["min_level"], group_s["max_level"])
                # armor.strength_level = 5
                # armor.strength_exp = 0
                # armor.property_index = 0
                # armor.is_lock = False
                items.append(item_detail)
                armor_num -= 1
                break
    return items


def make_SceneDataNotice(session):
    rsp = pb.SceneDataNotice()
    rsp.status = pb.StatusCode_OK
    data = rsp.data
    data.scene_id = session.scene_id
    data.players.add().CopyFrom(session.scene_player)
    for i in range(0, 12):
        tmp = data.collections.add()
        tmp.type = i
    for i in db.get_collection(session.player_id):
        crd = pb.PBCollectionRewardData()
        crd.ParseFromString(i[1])
        data.collections[i[0]].item_map[crd.item_id].CopyFrom(crd)

    for i in scene_data.get_scene_player(session.scene_id, session.channel_id):
        data.players.add().CopyFrom(i)
    data.channel_id = session.channel_id
    data.tod_time = int(notice_sync.tod_time)
    data.channel_label = session.channel_id
    return rsp
