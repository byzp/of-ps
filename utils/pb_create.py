from proto.net_pb2 import (
    Vector3,
    Character,
    SceneTeam,
    EPropertyType,
    SceneCharacterOutfitPreset,
    ItemDetail,
    EBagItemTag,
    StatusCode,
    SceneDataNotice,
    PBCollectionRewardData,
)
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
    team = SceneTeam()
    if char_ids[0]:
        char1 = team.char1
        char1.char_id = char_ids[0]

        chr = Character()
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

        # char1.pos.CopyFrom(Vector3())
        # char1.rot.CopyFrom(Vector3())
        char1.pos.x = 2394
        char1.pos.y = 908
        char1.rot.CopyFrom(Vector3())
    if char_ids[1]:
        char2 = team.char2
        char2.char_id = char_ids[1]

        chr = Character()
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
        char2.rot.CopyFrom(Vector3())
    if char_ids[2]:
        char3 = team.char3
        char3.char_id = char_ids[2]

        chr = Character()
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
        char3.rot.CopyFrom(Vector3())
    return team


def make_SceneCharacterOutfitPreset(player_id, outfit):
    sc = SceneCharacterOutfitPreset()
    item = ItemDetail()
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
            match i["new_bag_item_tag"]:
                case EBagItemTag.EBagItemTag_Weapon:  # 武器 tag:2
                    for weapon_i in res["Weapon"]["weapon"]["datas"]:
                        if weapon_i["i_d"] == item_id:
                            item_detail = ItemDetail()
                            item_detail.pack_type = (
                                ItemDetail.PackType.PackType_TempStorageArea
                            )
                            tmp = item_detail.main_item
                            if not weapon_i.get("item_i_d"):
                                continue
                            tmp.item_id = weapon_i["item_i_d"]
                            tmp.item_tag = EBagItemTag.EBagItemTag_Weapon
                            weapon = tmp.weapon
                            weapon.weapon_id = weapon_i["item_i_d"]
                            weapon.instance_id = db.get_instance_id(player_id)
                            for prop in res["Weapon"]["weapon_property"]["datas"]:
                                if weapon_i["weapon_property_i_d"] == prop["i_d"]:
                                    weapon.property_index = random.randint(
                                        1, len(prop["weapon_property_group_info"])
                                    )
                                    group_s = prop["weapon_property_group_info"][
                                        weapon.property_index - 1
                                    ]
                                    if not group_s.get("min_attack"):
                                        continue
                                    weapon.attack = int(
                                        random.uniform(
                                            group_s["min_attack"], group_s["max_attack"]
                                        )
                                    )
                                    weapon.damage_balance = int(
                                        random.uniform(
                                            group_s["min_damage_balance"],
                                            group_s["max_damage_balance"],
                                        )
                                    )
                                    weapon.critical_ratio = int(
                                        random.uniform(
                                            group_s["min_critical_ratio"],
                                            group_s["max_critical_ratio"],
                                        )
                                    )
                                    weapon.level = random.randint(
                                        group_s["min_level"], group_s["max_level"]
                                    )
                                    return item_detail
                case EBagItemTag.EBagItemTag_Armor:  # 防具 tag:3
                    for armor_i in res["Armor"]["armor"]["datas"]:
                        if armor_i["i_d"] == item_id:
                            item_detail = ItemDetail()
                            tmp = item_detail.main_item
                            tmp.item_id = armor_i["i_d"]
                            tmp.item_tag = EBagItemTag.EBagItemTag_Armor
                            # tmp.is_new = False
                            armor = tmp.armor
                            armor.armor_id = armor_i["i_d"]
                            armor.instance_id = db.get_instance_id(player_id)
                            for prop in res["Armor"]["armor_property"]["datas"]:
                                if armor_i["armor_property_i_d"] == prop["i_d"]:
                                    armor.property_index = random.randint(
                                        1, len(prop["armor_property_group_info"])
                                    )
                                    group_s = prop["armor_property_group_info"][
                                        armor.property_index - 1
                                    ]
                                    prop_group = {
                                        EPropertyType.EPropertyType_ExtHp: [
                                            "min_ext_hp",
                                            "max_ext_hp",
                                        ],
                                        EPropertyType.EPropertyType_MaxHPPercent: [
                                            "min_hp_percent",
                                            "max_hp_percent",
                                        ],
                                        EPropertyType.EPropertyType_ExtAttack: [
                                            "min_ext_attack",
                                            "max_ext_attack",
                                        ],
                                        EPropertyType.EPropertyType_AttackPercent: [
                                            "min_attack_percent",
                                            "max_attack_percent",
                                        ],
                                        EPropertyType.EPropertyType_ExtDefense: [
                                            "min_ext_defense",
                                            "max_ext_defense",
                                        ],
                                        EPropertyType.EPropertyType_DefensePercent: [
                                            "min_defense_percent",
                                            "max_defense_percent",
                                        ],
                                        EPropertyType.EPropertyType_CriticalRatio: [
                                            "min_critical_ratio",
                                            "max_critical_ratio",
                                        ],
                                        EPropertyType.EPropertyType_CriticalDamagePercent: [
                                            "min_critical_damage_percent",
                                            "max_critical_damage_percent",
                                        ],
                                        EPropertyType.EPropertyType_RecoverPercent: [
                                            "min_recover_percent",
                                            "max_recover_percent",
                                        ],
                                    }
                                    armor.main_property_type = random.choice(
                                        list(prop_group.keys())
                                    )
                                    armor.main_property_val = 0
                                    random.uniform(
                                        group_s[
                                            prop_group[armor.main_property_type][0]
                                        ],
                                        group_s[
                                            prop_group[armor.main_property_type][1]
                                        ],
                                    )
                                    armor.wearer_id = 0
                                    armor.level = random.randint(
                                        group_s["min_level"], group_s["max_level"]
                                    )
                                    # armor.strength_level = 5
                                    # armor.strength_exp = 0
                                    # armor.property_index = 0
                                    # armor.is_lock = False
                                    return item_detail

                case EBagItemTag.EBagItemTag_Poster:  # 映像 tag:5
                    item_detail = ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    poster = tmp.poster
                    poster.poster_id = i["i_d"]
                    poster.instance_id = db.get_instance_id(player_id)
                    poster.star = 1
                    return item_detail

                case EBagItemTag.EBagItemTag_Inscription:  # 铭文 tag:17
                    item_detail = ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.inscription.inscription_id = i["i_d"]
                    tmp.inscription.level = 1
                    return item_detail

                case EBagItemTag.EBagItemTag_Card:  # 收藏卡 tag:7
                    item_detail = ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.character.character_id = i["i_d"]
                    return item_detail
                    # 这个好像是多余的角色碎片转换成星辰后，删除角色碎片的通知
                case _:
                    # EBagItemTag.EBagItemTag_Gift:  # 礼包 tag:1
                    # EBagItemTag.EBagItemTag_Fragment:  # 角色碎片 tag:4
                    # EBagItemTag.EBagItemTag_Collection:  # 收藏品 tag:6
                    # EBagItemTag.EBagItemTag_Material:  # 材料 tag:8
                    # EBagItemTag.EBagItemTag_Currency:  # 货币 tag:9
                    # EBagItemTag.EBagItemTag_Food:  # 食物 tag:10
                    # EBagItemTag.EBagItemTag_SpellCard
                    # EBagItemTag.EBagItemTag_Item:  # 普通道具 tag:12
                    # EBagItemTag.EBagItemTag_Fish:  # 鱼产 tag:13
                    # EBagItemTag.EBagItemTag_Recipe
                    # EBagItemTag.EBagItemTag_Baitbox:  # 鱼饵箱 tag:15
                    # EBagItemTag.EBagItemTag_Quest
                    # EBagItemTag.EBagItemTag_StrengthStone:  # 强化石 tag:18
                    # EBagItemTag.EBagItemTag_ExpBook:  # 经验书 能量饮料 tag:19
                    # EBagItemTag.EBagItemTag_Head:  # 头像 tag:20
                    # EBagItemTag.EBagItemTag_Fashion:  # 时装 tag:21
                    # EBagItemTag.EBagItemTag_UnlockItem:  # 解锁道具 tag:22
                    # EBagItemTag.EBagItemTag_AbilityItem:  # 能力道具 tag:23
                    # EBagItemTag.EBagItemTag_UnlockAbilityItem:  # 解锁能力道具 tag:24
                    # EBagItemTag.EBagItemTag_CharacterBadge:  # 角色徽章 tag:25
                    # EBagItemTag.EBagItemTag_DyeStuff
                    # EBagItemTag.EBagItemTag_PlayerExp
                    # EBagItemTag.EBagItemTag_WorldLevel
                    # EBagItemTag.EBagItemTag_Agentia:  # 特殊道具 女装之魂 蔷薇之心 等 tag:29
                    # EBagItemTag.EBagItemTag_MoonStone:  # 月石 技能材料 tag:30
                    # EBagItemTag.EBagItemTag_Umbrella:  # 伞 tag:31
                    # EBagItemTag.EBagItemTag_Vitality:  # 体力药剂 tag:32
                    # EBagItemTag.EBagItemTag_Badge:  # 头衔 tag:33
                    # EBagItemTag.EBagItemTag_Furniture:  # 家具 tag:34
                    # EBagItemTag.EBagItemTag_Energy:  # 精力药水 tag:35
                    # EBagItemTag.EBagItemTag_ShowWeapon
                    # EBagItemTag.EBagItemTag_ShowArmor
                    # EBagItemTag.EBagItemTag_TeleportKey:  # 采集空间钥匙 tag:38
                    # EBagItemTag.EBagItemTag_WallPaper:  # 壁纸 tag:39
                    # EBagItemTag.EBagItemTag_Expression
                    # EBagItemTag.EBagItemTag_MoonCard:  # 月卡通知也许 未发现实际内容 tag:41
                    # EBagItemTag.EBagItemTag_PhoneCase:  # 手机壁纸 tag:42
                    # EBagItemTag.EBagItemTag_Pendant:  # 挂件 tag:43
                    # EBagItemTag.EBagItemTag_AvatarFrame:  # 头像框 tag:44
                    # EBagItemTag.EBagItemTag_IntimacyGift:  # 亲密度礼物 tag:45
                    # EBagItemTag.EBagItemTag_MusicNote:  # 音乐册 tag:46
                    # EBagItemTag.EBagItemTag_MonthlyCard:  # 月度卡 未知 tag:47
                    # EBagItemTag.EBagItemTag_BattlePassCard:  # 战斗通行证 未知 tag:48
                    # EBagItemTag.EBagItemTag_MonthlyGiftCard:  # 月度礼物卡 tag:49
                    # EBagItemTag.EBagItemTag_BattlePassGiftCard # 战斗通行证礼物卡 tag:50
                    # EBagItemTag.EBagItemTag_SeasonalMiniGamesItem:  # 小游戏道具 tag:51
                    # EBagItemTag.EBagItemTag_Vehicle
                    item_detail = ItemDetail()
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num
                    item_detail.extra_quality = i.get("quality", 0)
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
        item_detail = ItemDetail()
        item_detail.pack_type = ItemDetail.PackType.PackType_TempStorageArea
        tmp = item_detail.main_item
        if not weapon_i.get("item_i_d"):
            continue
        tmp.item_id = weapon_i["item_i_d"]
        tmp.item_tag = EBagItemTag.EBagItemTag_Weapon
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
        item_detail = ItemDetail()
        tmp = item_detail.main_item
        tmp.item_id = armor_i["i_d"]
        tmp.item_tag = EBagItemTag.EBagItemTag_Armor
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
                    EPropertyType.EPropertyType_ExtHp: ["min_ext_hp", "max_ext_hp"],
                    EPropertyType.EPropertyType_MaxHPPercent: [
                        "min_hp_percent",
                        "max_hp_percent",
                    ],
                    EPropertyType.EPropertyType_ExtAttack: [
                        "min_ext_attack",
                        "max_ext_attack",
                    ],
                    EPropertyType.EPropertyType_AttackPercent: [
                        "min_attack_percent",
                        "max_attack_percent",
                    ],
                    EPropertyType.EPropertyType_ExtDefense: [
                        "min_ext_defense",
                        "max_ext_defense",
                    ],
                    EPropertyType.EPropertyType_DefensePercent: [
                        "min_defense_percent",
                        "max_defense_percent",
                    ],
                    EPropertyType.EPropertyType_CriticalRatio: [
                        "min_critical_ratio",
                        "max_critical_ratio",
                    ],
                    EPropertyType.EPropertyType_CriticalDamagePercent: [
                        "min_critical_damage_percent",
                        "max_critical_damage_percent",
                    ],
                    EPropertyType.EPropertyType_RecoverPercent: [
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
    rsp = SceneDataNotice()
    rsp.status = StatusCode.StatusCode_OK
    data = rsp.data
    data.scene_id = session.scene_id
    pos = session.pos.get(session.scene_id)
    if pos:
        session.scene_player.team.char1.pos.CopyFrom(pos)
    data.players.add().CopyFrom(session.scene_player)
    for i in range(0, 12):
        tmp = data.collections.add()
        tmp.type = i
    for i in db.get_collection(session.player_id):
        crd = PBCollectionRewardData()
        crd.ParseFromString(i[1])
        data.collections[i[0]].item_map[crd.item_id].CopyFrom(crd)
    for furniture in db.get_furniture(
        session.scene_id, session.channel_id
    ):  # (scene_id, channel_id, player_id, furniture_id,furniture_detail_blob)
        data.scene_garden_data.garden_furniture_info_map[furniture[3]].ParseFromString(
            furniture[4]
        )

    for i in scene_data.get_scene_player(session.scene_id, session.channel_id):
        data.players.add().CopyFrom(i)
    data.channel_id = session.channel_id
    data.tod_time = int(notice_sync.tod_time)
    data.channel_label = session.channel_id
    return rsp
