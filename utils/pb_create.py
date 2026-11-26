from server.scene_data import get_session

import datetime as _dt

import calendar
import time
from proto.net_pb2 import (
    Vector3,
    Character,
    SceneTeam,
    EPropertyType,
    SceneCharacterOutfitPreset,
    OutfitPreset,
    ItemDetail,
    EBagItemTag,
    StatusCode,
    SceneDataNotice,
    PBCollectionRewardData,
    PlayerBriefInfo,
    Quest,
    QuestStatus,
    QuestNotice,
    Achieve,
    TreasureBoxData,
    TreasureBoxLocType_DUNGEON,
    BattleState,
)
from network.msg_id import MsgId
from config import Config
import utils.db as db
from datetime import datetime
from utils.res_loader import res
import random
import server.scene_data as scene_data
import server.notice_sync as notice_sync
from utils import flag_config, flag_state, collection_state, weather
from utils import treasure_box as tb_idx


def make_ScenePlayer(session):
    # 构造ScenePlayer
    player = session.scene_player
    player.player_id = session.player_id
    player.player_name = session.player_name

    player.food_buff_ids.clear()
    player.global_buff_ids.clear()

    birthday_str, char_ids = db.get_players_info(session.player_id, "birthday,team")
    if birthday_str:
        # 历史脏数据容错: 仅 %Y-%m-%d 形状且日期合法时才解析(strptime 唯一抛点)
        valid_date = (
            isinstance(birthday_str, str)
            and len(birthday_str) == 10
            and birthday_str[:4].isdigit()
            and birthday_str[4] == "-"
            and birthday_str[5:7].isdigit()
            and birthday_str[7] == "-"
            and birthday_str[8:10].isdigit()
        )
        if valid_date:
            year_i, month_i, day_i = (
                int(birthday_str[:4]),
                int(birthday_str[5:7]),
                int(birthday_str[8:10]),
            )
            valid_date = (
                1 <= year_i <= 9999
                and 1 <= month_i <= 12
                and 1 <= day_i <= calendar.monthrange(year_i, month_i)[1]
            )
        if valid_date:
            birthday_date = datetime.strptime(birthday_str, "%Y-%m-%d")
            today = datetime.now()
            player.is_birthday = (
                today.month == birthday_date.month and today.day == birthday_date.day
            )
        else:
            player.is_birthday = False
    else:
        player.is_birthday = False  # 判断生日

    saved_position = session.pos.get(session.scene_id)
    saved_rotation = player.team.char1.rot.SerializeToString()
    player.team.CopyFrom(make_SceneTeam(session.player_id, char_ids))
    if saved_position is not None:
        player.team.char1.pos.CopyFrom(saved_position)
    if saved_rotation:
        player.team.char1.rot.ParseFromString(saved_rotation)


def _fill_scene_equip(player_id, char_msg, chr):
    """从角色当前装备方案填充防具/映像/铭文字段"""
    preset = None
    idx = chr.in_use_equipment_preset_index
    preset = next((p for p in chr.equipment_presets if p.preset_index == idx), None)
    if preset is None:
        return
    for a in preset.armors:
        if not a.armor_id:
            continue
        blob = db.get_item_detail(player_id, None, a.armor_id)
        if not blob:
            continue
        it = ItemDetail()
        it.ParseFromString(blob)
        base = char_msg.armors.add()
        base.armor_id = it.main_item.armor.armor_id
        base.armor_star = it.main_item.armor.strength_level
    for pp in preset.posters:
        if not pp.poster_id:
            continue
        blob = db.get_item_detail(player_id, None, pp.poster_id)
        if blob:
            item = ItemDetail()
            item.ParseFromString(blob)
            bp = char_msg.posters.add()
            bp.poster_id = item.main_item.poster.poster_id
            bp.poster_star = item.main_item.poster.star


def _in_use_outfit_preset(chr):
    """按当前索引查找外观预设, 兼容旧数据的非顺序列表。"""
    idx = chr.in_use_outfit_preset_index
    for preset in chr.outfit_presets:
        if preset.preset_index == idx:
            return preset
    if 0 <= idx < len(chr.outfit_presets):
        return chr.outfit_presets[idx]
    return None


def _default_outfit_preset(chr):
    """角色缺少外观预设时, 从 Character 表构造默认预设。"""
    for cfg in res.get("Character", {}).get("character", {}).get("datas", ()):
        if not isinstance(cfg, dict) or cfg.get("i_d") != chr.character_id:
            continue
        preset = OutfitPreset()
        preset.preset_index = chr.in_use_outfit_preset_index
        preset.hat = cfg.get("hat_i_d") or 0
        preset.hair = cfg.get("hair_i_d") or 0
        preset.clothes = cfg.get("cloth_i_d") or 0
        ornaments = cfg.get("orn_i_d")
        if isinstance(ornaments, (list, tuple)) and ornaments:
            preset.ornament = ornaments[0]
        return preset
    return None


def _outfit_preset_is_empty(preset):
    return not any((preset.hat, preset.hair, preset.clothes, preset.ornament))


def _effective_outfit_preset(chr):
    """返回角色当前外观；旧数据中的空预设回退到角色默认外观。"""
    preset = _in_use_outfit_preset(chr)
    if preset is None or _outfit_preset_is_empty(preset):
        preset = _default_outfit_preset(chr)
    return preset


def _copy_dye_scheme(dst, item, index):
    """染色方案越界安全拷贝: 未解锁/索引无效(含空方案表)时回退默认空方案"""
    schemes = item.main_item.outfit.dye_schemes
    if 0 <= index < len(schemes):
        dst.CopyFrom(schemes[index])
    else:
        dst.Clear()


def make_SceneTeam(player_id, char_ids, team=None, dungeon_id=0):
    if team is None:
        team = SceneTeam()
    else:
        # make_SceneTeam 也被副本/深渊复用; 复用输出消息时必须丢弃旧角色的
        # outfit_preset, armors 和 posters, 否则新角色会继承旧角色的外观。
        team.Clear()

    dungeon = (
        next(
            (
                row
                for row in res["ScenesConfigAsset"]["Dungeons"]
                if row["ID"] == dungeon_id
            ),
            None,
        )
        if dungeon_id
        else None
    )
    born = dungeon.get("Born", ()) if dungeon else ()
    scene_chars = (team.char1, team.char2, team.char3)
    for index, char_msg in enumerate(scene_chars):
        char_id = char_ids[index] if index < len(char_ids) else 0
        if not char_id:
            continue

        owned = db.get_characters(player_id, char_id)
        # 角色尚未拥有(如副本请求中的非法角色)时保持该队伍位为空。
        if not owned:
            continue

        chr = Character()
        chr.ParseFromString(owned[0])
        char_msg.char_id = char_id

        preset = _effective_outfit_preset(chr)
        if preset is not None:
            make_SceneCharacterOutfitPreset(player_id, preset, char_msg.outfit_preset)

        char_msg.character_appearance.CopyFrom(chr.character_appearance)
        char_msg.char_lv = chr.level
        char_msg.char_star = chr.star
        char_msg.char_break_lv = chr.max_level
        if chr.equipment_presets:
            current = next(
                (
                    p
                    for p in chr.equipment_presets
                    if p.preset_index == chr.in_use_equipment_preset_index
                ),
                None,
            )
            blob = (
                db.get_item_detail(player_id, None, current.weapon)
                if current and current.weapon
                else None
            )
            if blob:
                item = ItemDetail()
                item.ParseFromString(blob)
                char_msg.weapon_id = item.main_item.weapon.weapon_id
                char_msg.weapon_star = item.main_item.weapon.star
        char_msg.gather_weapon = chr.gather_weapon  # 设置采集武器
        _fill_scene_equip(player_id, char_msg, chr)

        if dungeon_id:
            spawn = born[index] if index < len(born) else (born[0] if born else {})
            for axis in ("x", "y", "z"):
                setattr(
                    char_msg.pos,
                    axis,
                    int(spawn.get("Position", {}).get(axis, 0) * 100),
                )
                setattr(
                    char_msg.rot,
                    axis,
                    int(spawn.get("Rotation", {}).get(axis, 0) * 100),
                )
        else:
            char_msg.pos.x = 2394
            char_msg.pos.y = 908
            char_msg.rot.CopyFrom(Vector3())
    return team


def _fill_scene_outfit_slot(
    player_id, sc, outfit_id, field_name, dye_field_name, dye_index
):
    if not outfit_id:
        return
    setattr(sc, field_name, outfit_id)
    blob = db.get_item_detail(player_id, outfit_id)
    if not blob:
        getattr(sc, dye_field_name).Clear()
        return
    item = ItemDetail()
    item.ParseFromString(blob)
    _copy_dye_scheme(getattr(sc, dye_field_name), item, dye_index)


def make_SceneCharacterOutfitPreset(player_id, outfit, sc=None):
    if sc == None:
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


def _property_group_index(groups, level):
    if level is None:
        return random.randint(1, len(groups))
    for index, group in enumerate(groups, 1):
        if group.get("min_level", 0) <= level <= group.get("max_level", 0):
            return index
    raise ValueError(f"装备等级{level}不在资源属性区间内")


def make_item(
    item_id, num=1, player_id=0, item_detail=None, is_all=False, equipment_level=None
) -> list:
    r = []
    if item_detail == None:
        item_detail = ItemDetail()
    for i in res["Item"]["item"]["datas"]:
        if is_all or i["i_d"] == item_id:
            item_detail.extra_quality = i.get("quality", 0)
            match i["new_bag_item_tag"]:
                case EBagItemTag.EBagItemTag_Weapon:  # 武器 tag:2
                    for weapon_i in res["Weapon"]["weapon"]["datas"]:
                        if weapon_i["i_d"] == i["i_d"]:
                            tmp = item_detail.main_item
                            if not weapon_i.get("item_i_d"):
                                continue
                            tmp.item_id = weapon_i["item_i_d"]
                            tmp.item_tag = EBagItemTag.EBagItemTag_Weapon
                            weapon = tmp.weapon
                            weapon.weapon_id = weapon_i["item_i_d"]
                            weapon.instance_id = db.get_instance_id(player_id)
                            f = True
                            for prop in res["Weapon"]["weapon_property"]["datas"]:
                                if weapon_i["weapon_property_i_d"] == prop["i_d"]:
                                    weapon.property_index = _property_group_index(
                                        prop["weapon_property_group_info"],
                                        equipment_level,
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
                                        * 100
                                    )
                                    weapon.critical_ratio = int(
                                        random.uniform(
                                            group_s["min_critical_ratio"],
                                            group_s["max_critical_ratio"],
                                        )
                                        * 100
                                    )
                                    weapon.level = (
                                        equipment_level
                                        if equipment_level is not None
                                        else random.randint(
                                            group_s["min_level"], group_s["max_level"]
                                        )
                                    )
                                    weapon.star = 1
                                    f = False
                                    break
                            if f:
                                # 无属性的,鱼竿,载具等
                                item_detail.pack_type = 0
                                weapon.attack = 1
                                weapon.damage_balance = 1
                                weapon.critical_ratio = 1
                                weapon.level = 1
                                weapon.star = 1
                                weapon.durability = 100
                                weapon.property_index = 1
                            if is_all:
                                r.append(item_detail)
                                item_detail = ItemDetail()
                                break
                            return item_detail
                case EBagItemTag.EBagItemTag_Armor:  # 防具 tag:3
                    for armor_i in res["Armor"]["armor"]["datas"]:
                        if armor_i["i_d"] == i["i_d"]:
                            tmp = item_detail.main_item
                            tmp.item_id = armor_i["i_d"]
                            tmp.item_tag = EBagItemTag.EBagItemTag_Armor
                            # tmp.is_new = False
                            armor = tmp.armor
                            armor.armor_id = armor_i["i_d"]
                            armor.instance_id = db.get_instance_id(player_id)
                            for prop in res["Armor"]["armor_property"]["datas"]:
                                if armor_i["armor_property_i_d"] == prop["i_d"]:
                                    armor.property_index = _property_group_index(
                                        prop["armor_property_group_info"],
                                        equipment_level,
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
                                    val = random.uniform(
                                        group_s[
                                            prop_group[armor.main_property_type][0]
                                        ],
                                        group_s[
                                            prop_group[armor.main_property_type][1]
                                        ],
                                    )
                                    armor.main_property_val = (
                                        int(val)
                                        if armor.main_property_type
                                        in [
                                            EPropertyType.EPropertyType_ExtHp,
                                            EPropertyType.EPropertyType_ExtAttack,
                                            EPropertyType.EPropertyType_ExtDefense,
                                        ]
                                        else int(val * 100)
                                    )
                                    armor.wearer_id = 0
                                    armor.level = (
                                        equipment_level
                                        if equipment_level is not None
                                        else random.randint(
                                            group_s["min_level"], group_s["max_level"]
                                        )
                                    )
                                    # armor.strength_level = 5
                                    # armor.strength_exp = 0
                                    break
                            if is_all:
                                r.append(item_detail)
                                item_detail = ItemDetail()
                                break
                            return item_detail

                case EBagItemTag.EBagItemTag_Poster:  # 映像 tag:5
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    poster = tmp.poster
                    poster.poster_id = i["i_d"]
                    poster.instance_id = db.get_instance_id(player_id)
                    poster.star = 1
                    if is_all:
                        r.append(item_detail)
                        item_detail = ItemDetail()
                        continue
                    return item_detail

                case EBagItemTag.EBagItemTag_Fashion:  # 时装 tag:21
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    outfit = tmp.outfit
                    outfit.outfit_id = i["i_d"]
                    dye_scheme = outfit.dye_schemes.add()
                    dye_scheme.is_un_lock = True
                    if is_all:
                        r.append(item_detail)
                        item_detail = ItemDetail()
                        continue
                    return item_detail

                case EBagItemTag.EBagItemTag_Inscription:  # 铭文 tag:17
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.inscription.inscription_id = i["i_d"]
                    tmp.inscription.level = 1
                    if is_all:
                        r.append(item_detail)
                        item_detail = ItemDetail()
                        continue
                    return item_detail

                case EBagItemTag.EBagItemTag_Card:  # 收藏卡 tag:7
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.character.character_id = i["i_d"]
                    if is_all:
                        r.append(item_detail)
                        item_detail = ItemDetail()
                        continue
                    return item_detail
                    # 这个好像是多余的角色碎片转换成星辰后，删除角色碎片的通知
                case EBagItemTag.EBagItemTag_TreasureMap:  # 藏宝图 tag:53
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    treasure = tmp.treasure
                    treasure.item_id = i["i_d"]
                    treasure.instance_id = db.get_instance_id(player_id)
                    treasure.scene_id = _treasure_scene_id(player_id)
                    if is_all:
                        r.append(item_detail)
                        item_detail = ItemDetail()
                        continue
                    return item_detail
                case EBagItemTag.EBagItemTag_Pet:  # 宠物 tag:56
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    pet = tmp.pet
                    pet.item_id = i["i_d"]
                    pet.instance_id = db.get_instance_id(player_id)
                    pet.level = 1
                    nature_datas = res["Pet"]["nature"]["datas"]
                    pet.nature_id = random.choice(nature_datas)["i_d"]
                    completeness_datas = res["Pet"]["completeness"]["datas"]
                    pet.integrity_id = random.choice(completeness_datas)["i_d"]
                    pet.catch_scene_id = 1
                    pet.catch_time = int(time.time())
                    pet.size = random.randint(80, 150)
                    pet.weight = random.randint(100000, 300000)
                    attrs = [0, 1, 2, 3, 4, 5]
                    random.shuffle(attrs)
                    num_integrity = random.randint(2, 4)
                    for attr in attrs[:num_integrity]:
                        integrity = pet.integrity.add()
                        integrity.attr = attr
                        base_stat = i.get(
                            ("hp", "pow", "str", "int", "dex", "luc")[attr], 50
                        )
                        integrity.value = random.randint(
                            max(1, base_stat // 10), max(1, base_stat // 3)
                        )
                    if is_all:
                        r.append(item_detail)
                        item_detail = ItemDetail()
                        continue
                    return item_detail
                case _:
                    # EBagItemTag.EBagItemTag_Gift: # 礼包 tag:1
                    # EBagItemTag.EBagItemTag_Fragment: # 角色碎片 tag:4
                    tmp = item_detail.main_item
                    tmp.item_id = i["i_d"]
                    tmp.item_tag = i["new_bag_item_tag"]
                    tmp.base_item.item_id = i["i_d"]
                    tmp.base_item.num = num
                    if is_all:
                        r.append(item_detail)
                        item_detail = ItemDetail()
                        continue
                    return item_detail
    return r


def _treasure_scene_id(player_id):
    """藏宝图可用场景: 取玩家当前所在场景(server.scene_data 会话表), 兜底 1"""

    for s in get_session():
        if s.player_id == player_id:
            return s.scene_id or 1
    return 1


def _scene_types():
    """Scene.scene {i_d: new_scene_type}: 1/3=开放空间, 2=副本类(深渊/
    异变/模拟/活动/采集岛)"""
    global _SCENE_TYPES
    if _SCENE_TYPES is None:
        _tab = res.get("Scene")
        _tab = _tab.get("scene") if isinstance(_tab, dict) else None
        _tab = _tab.get("datas") if isinstance(_tab, dict) else None
        _SCENE_TYPES = {
            r["i_d"]: r.get("new_scene_type")
            for r in (_tab if isinstance(_tab, (list, tuple)) else [])
            if isinstance(r, dict) and "i_d" in r
        }
    return _SCENE_TYPES


_SCENE_TYPES = None


def make_treasure_box_item(
    player_id,
    world_level,
    num=0,
    scene_id=None,
    box_id=None,
) -> list:
    """普通箱基础金币加随机装备/材料；缺失的服务端掉落参数见Config。"""
    if (
        scene_id is not None
        and _scene_types().get(scene_id) == Config.INSTANCE_SCENE_TYPE
    ):
        return []
    player_level = db.get_players_info(player_id, "level")[0]
    world = next(
        (
            row
            for row in res["Level"]["world_level"]["datas"]
            if row["i_d"] == max(1, world_level)
        ),
        {},
    )
    max_level = max(1, min(player_level, world.get("monster_level", player_level)))
    weapons = {
        row["item_i_d"]
        for row in res["Weapon"]["weapon"]["datas"]
        if row.get("item_i_d") and row.get("new_weapon_system_type") in (1, 2, 3, 4, 5)
    }
    armors = {row["i_d"] for row in res["Armor"]["armor"]["datas"]}
    pools = {tag: [] for tag in (2, 3)}
    for row in res["Item"]["item"]["datas"]:
        tag, iid = row.get("new_bag_item_tag"), row["i_d"]
        valid = iid in (weapons if tag == 2 else armors)
        if tag in pools and valid and row.get("quality", 0) <= max(1, world_level):
            pools[tag].append(iid)
    items = _make_box_extra(*Config.NORMAL_BOX_CURRENCY, player_id)
    kinds = [tag for tag in pools if pools[tag]]
    count = num or random.randint(*Config.NORMAL_BOX_EQUIPMENT_COUNT)
    for _ in range(count if kinds else 0):
        tag = random.choice(kinds)
        item = make_item(
            random.choice(pools[tag]),
            1,
            player_id,
            equipment_level=random.randint(1, max_level),
        )
        item.pack_type = ItemDetail.PackType.PackType_TempStorageArea
        items.append(item)
    if (
        box_id != Config.BATTLE_TREASURE_BOX_ID
        and random.random() < Config.NORMAL_BOX_MATERIAL_CHANCE
    ):
        iid = random.choice(Config.NORMAL_BOX_MATERIAL_IDS)
        items.extend(
            _make_box_extra(
                iid, random.randint(*Config.NORMAL_BOX_MATERIAL_COUNT), player_id
            )
        )
    return items


# 一次性收集宝箱特殊奖励主题池(Item.new_bag_item_tag):
# 21=时装, 26=染剂, 31=伞; 缺省按 box_id 轮换(见 make_collection_box_reward)
_box_pools_cache = None


def _box_pools():
    global _box_pools_cache
    if _box_pools_cache is None:
        pools = {}
        for r in res.get("Item", {}).get("item", {}).get("datas", []):
            if not isinstance(r, dict):
                continue
            tag = r.get("new_bag_item_tag")
            if tag in (21, 26, 31) and r.get("i_d"):
                pools.setdefault(tag, []).append(r["i_d"])
        _box_pools_cache = pools
    return _box_pools_cache


def _make_box_extra(item_id, num, player_id):
    d = make_item(item_id, num, player_id)
    if isinstance(d, ItemDetail):
        return [d]
    return []


def make_collection_box_reward(
    player_id,
    box_id,
    reward_type=None,
) -> list:
    """生成一次性不可刷新宝箱的唯一特殊资源。

    reward_type 仅决定资源池: 1=时装, 2/4=染剂, 3=伞。缺省时按
    box_id 做确定性轮换。奖励列表必须只有一个 ItemDetail, 领取时由
    TreasureBoxPickup 交给 item_mgr 持久化并登记为已获得。"""
    reward = Config.COLLECTION_BOX_REWARDS.get(box_id)
    if reward:
        return _make_box_extra(*reward, player_id)
    pools = _box_pools()

    def _pick(tag):
        ids = pools.get(tag) or []
        if not ids:
            return None
        idx = (player_id * 2654435761 ^ box_id * 97 ^ tag * 31) % len(ids)
        return ids[idx]

    theme = (reward_type if reward_type in (1, 2, 3, 4) else None) or (
        box_id % 3 + 1
    )  # 缺省主题轮换 1时装/2染剂/3伞
    tag = {
        1: 21,  # 时装
        2: 26,  # 染剂
        3: 31,  # 伞
        4: 26,  # 染剂
    }.get(theme, 21)
    item_id = _pick(tag)
    if not item_id:
        return []
    return _make_box_extra(item_id, 1, player_id)


def make_scene_treasure_boxes(session, include_dynamic=True):
    """回放有效记录；教学场景额外保留官服的未开启宝箱初始化条目。"""
    dungeon = getattr(session, "dungeon", None)
    dungeon_id = dungeon[0] if dungeon else 0
    tb_idx.expire_due_records(
        session.player_id,
        scene_id=session.scene_id,
        dungeon_id=dungeon_id,
    )
    boxes = []

    # SceneDataNotice 与 DungeonEnterRsp 共用点位解析和持久状态回放。
    tb_types = {
        r["i_d"]: r.get("new_treasure_box_type", 1)
        for r in res["TreasureBox"]["treasure_box"]["datas"]
        if isinstance(r, dict) and r.get("i_d")
    }

    def _fill_tb(tbd, index, box_id, store_key):
        tbd.index = index
        tbd.box_id = box_id
        tbd.type = tb_types.get(box_id, 1)
        blob, used_legacy = tb_idx.load_record(session.player_id, store_key, index)
        if not blob:
            # 副本Enter/RepeatEnter初始化本轮箱，教学初始化30001/30002。
            # 普通世界仍省略无记录点位；初始化不写数据库占位记录。
            return bool(dungeon_id) or session.scene_id == Config.TUTORIAL_SCENE_ID
        saved = TreasureBoxData()
        saved.ParseFromString(blob)
        normalized_time = tb_idx.normalize_refresh_time(saved.next_refresh_time)
        record_key = index if used_legacy else store_key
        if normalized_time != saved.next_refresh_time:
            saved.next_refresh_time = normalized_time
            db.set_treasure_box(
                session.player_id, record_key, saved.SerializeToString()
            )
        if isinstance(store_key, int) and not saved.rewards:
            return False
        interval = tb_idx.refresh_interval(box_id, is_dungeon=bool(dungeon_id))
        if interval > 0 and (
            (
                saved.next_refresh_time > 0
                and saved.next_refresh_time <= int(time.time())
            )
            or (saved.next_refresh_time == 0 and not saved.rewards)
        ):
            db.delete_treasure_box(session.player_id, record_key)
            return False
        if used_legacy:
            db.set_treasure_box(session.player_id, store_key, saved.SerializeToString())
            db.delete_treasure_box(session.player_id, index)
        tbd.state = saved.state
        tbd.next_refresh_time = saved.next_refresh_time * 1000
        tbd.rewards.extend(saved.rewards)
        return True

    loc_type = TreasureBoxLocType_DUNGEON if dungeon_id else 0
    if loc_type == TreasureBoxLocType_DUNGEON:
        collection_infos = next(
            (
                x.get("CollectionTreasureInfos") or ()
                for x in res.get("ScenesConfigAsset", {}).get("Dungeons", ())
                if isinstance(x, dict) and x.get("ID") == session.dungeon[0]
            ),
            (),
        )
    else:
        sc = next(
            (
                x
                for x in res["ScenesConfigAsset"]["Scenes"]
                if x.get("ID") == session.scene_id
            ),
            None,
        )
        collection_infos = sc.get("CollectionTreasureInfos") or () if sc else ()
    for pos, c in enumerate(collection_infos):
        if isinstance(c, dict) and c.get("ID"):
            index = c.get("Index", pos)
            store_key = tb_idx.static_store_key(session, index, loc_type)
            tbd = TreasureBoxData()
            if _fill_tb(tbd, index, c["ID"], store_key):
                boxes.append(tbd)
    if include_dynamic:
        for k in db.get_kv_keys(session.player_id, "dyn_box"):
            if not k.isdigit():
                continue
            v = db.get_kv(session.player_id, "dyn_box", k, "")
            idx = int(k)
            if v:
                tbd = TreasureBoxData()
                if _fill_tb(tbd, idx, int(v), -idx):
                    boxes.append(tbd)
    return boxes


def make_SceneDataNotice(session):
    rsp = SceneDataNotice()
    rsp.status = StatusCode.StatusCode_OK
    data = rsp.data
    data.scene_id = session.scene_id
    # 客户端DungeonSystem.OnInit用此列表重建已通关集合。
    # 登录/返回大场景均必须恢复真实记录，不能只在FinishRsp里同步。
    for dungeon_id, blob in sorted(db.get_dungeon(session.player_id).items()):
        data.dungeons.add().ParseFromString(blob)
    boxes = make_scene_treasure_boxes(session)
    for i in db.get_area(session.player_id, session.scene_id):
        data.areas.add().ParseFromString(i)
    data.treasure_boxes.extend(boxes)
    pos = session.pos.get(session.scene_id)
    if pos:
        session.scene_player.team.char1.pos.CopyFrom(pos)
    else:
        pos = session.scene_player.team.char1.pos
        rot = session.scene_player.team.char1.rot
        for i in res["ScenesConfigAsset"]["Scenes"]:
            if i["ID"] == session.scene_id:
                pos.x = int(i["Born"][0]["Position"]["x"] * 100)
                pos.y = int(i["Born"][0]["Position"]["y"] * 100)
                pos.z = int(i["Born"][0]["Position"]["z"] * 100)
                rot.y = int(i["Born"][0]["Rotation"]["y"] * 100)
                break
    data.players.add().CopyFrom(session.scene_player)
    for collection_type, items in collection_state.scene_items(
        session.player_id, session.scene_id
    ).items():
        collection = data.collections.add(type=collection_type)
        for item in items:
            collection.item_map[item.item_id].CopyFrom(item)
        collection_state.fill_progress(collection, session.scene_id, len(items))
    for i in db.get_challenge(session.player_id, session.scene_id):
        data.challenges.add().ParseFromString(i)
    for furniture in db.get_furniture(
        session.scene_id, session.channel_id
    ):  # (scene_id, channel_id, player_id, furniture_id,furniture_detail_blob)
        data.scene_garden_data.garden_furniture_info_map[furniture[3]].ParseFromString(
            furniture[4]
        )
    unlocked_flags = flag_state.visible_ids(session.player_id)
    for m in flag_config.flag_rows():
        if m.get("scene_i_d") != session.scene_id:
            continue
        flag_id = m["i_d"]
        if flag_state.is_battle_finished(session.player_id, flag_id):
            continue
        ic = m.get("icon_i_d")
        if ic == 8:
            # 活动秘境入口(场景>=100100 的副本): 仅活动期内显示
            if _event_dungeon_flag_visible(m):
                rsp.data.flag_ids.append(flag_id)
        elif flag_id in unlocked_flags or flag_config.is_default_flag(flag_id):
            # 常驻旗标来自 Manual/Flag 的默认配置；任务战斗入口只有
            # 在接受对应任务后进入持久化 scene_flags 才会出现。
            rsp.data.flag_ids.append(flag_id)

    battle_ids = set()
    for m in flag_config.flag_rows():
        if m.get("scene_i_d") != session.scene_id:
            continue
        for group in m.get("flag_group_info") or ():
            relation_id = group.get("relation_i_d")
            if (
                relation_id
                and relation_id not in battle_ids
                and db.get_kv(session.player_id, "flag_battle", f"b:{relation_id}", 0)
            ):
                battle_ids.add(relation_id)
                battle = data.flags.add()
                battle.battle_id = relation_id
                battle.state = BattleState.Finish
                battle.finish_times = 1
                battle.type = group.get("new_mission_type", 0)
                if battle.type == 1:
                    battle.voice_id = Config.SCENIC_VOICE_IDS.get(relation_id, 0)
    for i in scene_data.get_scene_player(session.scene_id, session.channel_id):
        if i.player_id != session.player_id:
            data.players.add().CopyFrom(i)
    data.channel_id = session.channel_id
    data.tod_time = int(notice_sync.tod_time)
    data.weather_type = weather.weather_at(int(notice_sync.game_time_seconds // 3600))
    data.channel_label = session.channel_id
    return rsp


_DUNGEON_INDEX = None


def _dungeon_index():
    """Dungeon.dungeon {i_d: row}(懒加载缓存)"""
    global _DUNGEON_INDEX
    if _DUNGEON_INDEX is None:
        _tab = res.get("Dungeon")
        _tab = _tab.get("dungeon") if isinstance(_tab, dict) else None
        _tab = _tab.get("datas") if isinstance(_tab, dict) else None
        _DUNGEON_INDEX = {
            r["i_d"]: r
            for r in (_tab if isinstance(_tab, (list, tuple)) else ())
            if isinstance(r, dict) and r.get("i_d")
        }
    return _DUNGEON_INDEX


def _event_dungeon_flag_visible(m, now=None):
    """活动秘境入口可见性: relation 副本 scene_i_d>=100100 判定为活动秘境,
    按 Config.EVENT_DUNGEON_WINDOWS(key=副本id 或 "*")的时间窗口放行。"""

    windows = getattr(Config, "EVENT_DUNGEON_WINDOWS", None)
    windows = windows if isinstance(windows, dict) else {}
    if not windows:
        return False
    dscenes = _dungeon_index()

    ts = now or _dt.datetime.now()
    for g in m.get("flag_group_info") or ():
        d = dscenes.get(g.get("relation_i_d"))
        _sid = d.get("scene_i_d") if d else None
        if isinstance(_sid, str):
            _sid = int(_sid) if _sid.strip().lstrip("+-").isdigit() else 0
        elif not isinstance(_sid, int):
            _sid = 0
        if not d or _sid < 100100:
            continue
        did = str(d["i_d"])
        win = windows.get(did) or windows.get("*")
        if not win or len(win) < 2:
            continue
        start = _dt.datetime.strptime(win[0], "%Y-%m-%d %H:%M:%S")
        end = _dt.datetime.strptime(win[1], "%Y-%m-%d %H:%M:%S")
        if start <= ts <= end:
            return True
    return False


def make_PlayerBriefInfo(player_id, info=None):
    # 获取在线玩家列表
    online_sessions = scene_data.get_session()
    online_player_ids = [s.player_id for s in online_sessions]
    if info == None:
        info = PlayerBriefInfo()
    info.is_online = player_id in online_player_ids
    (
        info.player_id,
        info.nick_name,
        info.level,
        info.head,
        info.last_login_time,
        info.sex,
        info.phone_background,
        info.sign,
        info.guild_name,
        info.team_leader_badge,
        info.character_id,
        info.create_time,
        info.player_label,
        info.garden_like_num,
        info.account_type,
        info.birthday,
        info.hide_value,
        info.avatar_frame,
    ) = db.get_players_info(
        player_id,
        "player_id,player_name,level,head,last_login_time,sex,phone_background,sign,guild_name,team_leader_badge,character_id,create_time,player_id,garden_like_num,account_type,birthday,hide_value,avatar_frame",
    )
    return info


def make_Quest(player_id, quest_id, q=None):
    if q == None:
        q = Quest()
    for i in res["Quest"]["quest"]["datas"]:
        if i["i_d"] == quest_id:
            q.quest_id = i["i_d"]
            q.status = QuestStatus.QuestStatus_InProgress
            q.bonus_times = 1
            for i2 in res["Quest"]["condition_set_group"]["datas"]:
                if i2["i_d"] == i["condition_set_group_i_d"]:
                    for i3 in i2["quest_condition_set"]:
                        for i4 in i3["achieve_condition_i_d"]:
                            c = q.conditions.add()
                            c.condition_id = i4
                            c.status = QuestStatus.QuestStatus_InProgress
                            blob = db.get_achieve(player_id, i4)
                            if blob:
                                achieve = Achieve()
                                achieve.ParseFromString(blob)
                                c.progress = achieve.count
                    return q


def make_QuestNotice(session, conds, qn=None):
    player_id = session.player_id
    if qn == None:
        qn = QuestNotice()
    for i in res["Quest"]["condition_set_group"]["datas"]:
        for i2 in i["quest_condition_set"]:
            for cond in conds:
                if cond in i2["achieve_condition_i_d"]:
                    blob = db.get_quest(player_id, i["i_d"])
                    if not blob:
                        # 任务尚未接受(如未接取对应主线剧情), 忽略该条件
                        continue
                    qn.status = StatusCode.StatusCode_OK
                    tmp = qn.quests.add()
                    tmp.ParseFromString(blob)
                    if tmp.status == QuestStatus.QuestStatus_Finish:
                        # 已完成(成就层 advance 已推链), 防双路径重复推进回退
                        continue
                    flag_state.unlock_for_quest(session, tmp)
                    sf_cond = True
                    for i3 in tmp.conditions:
                        if i3.condition_id == cond:
                            i3.status = QuestStatus.QuestStatus_Finish
                    quest_cfg = next(
                        (
                            row
                            for row in res["Quest"]["quest"]["datas"]
                            if row.get("i_d") == tmp.quest_id
                        ),
                        None,
                    )
                    condition_group = next(
                        (
                            row
                            for row in res["Quest"]["condition_set_group"]["datas"]
                            if row.get("i_d")
                            == (quest_cfg or {}).get("condition_set_group_i_d")
                        ),
                        None,
                    )
                    condition_sets = (
                        condition_group.get("quest_condition_set") or ()
                        if condition_group
                        else ()
                    )
                    if condition_sets:
                        sf_cond = any(
                            bool(condition_ids)
                            and all(
                                any(
                                    condition.condition_id == condition_id
                                    and condition.status
                                    == QuestStatus.QuestStatus_Finish
                                    for condition in tmp.conditions
                                )
                                for condition_id in condition_ids
                            )
                            for condition_ids in (
                                item.get("achieve_condition_i_d") or ()
                                for item in condition_sets
                            )
                        )
                    else:
                        sf_cond = all(
                            condition.status == QuestStatus.QuestStatus_Finish
                            for condition in tmp.conditions
                        )
                    if sf_cond:
                        tmp.status = QuestStatus.QuestStatus_Finish
                        session.quests.pop(tmp.quest_id, None)
                        # print(tmp.quest_id)
                        # for s in session.quests.keys():
                        quest_rows = res["Quest"]["quest"]["datas"]
                        pos = next(
                            (
                                index
                                for index, quest in enumerate(quest_rows)
                                if quest["i_d"] == i["i_d"]
                            ),
                            None,
                        )
                        if (
                            pos is not None
                            and pos + 1 < len(quest_rows)
                            and quest_rows[pos].get("quest_group")
                            and quest_rows[pos + 1].get("quest_group")
                            == quest_rows[pos].get("quest_group")
                        ):
                            q = qn.quests.add()
                            make_Quest(player_id, quest_rows[pos + 1]["i_d"], q)
                            db.set_quest(
                                player_id,
                                q.quest_id,
                                q.SerializeToString(),
                            )
                            session.quests[q.quest_id] = q
                            flag_state.unlock_for_quest(session, q)
                    db.set_quest(
                        player_id,
                        tmp.quest_id,
                        tmp.SerializeToString(),
                    )
                    return qn


def make_Achieve(session, params=None):
    if not Config.SKIP_QUESTS:
        cid = {}
        for i, q in session.quests.items():
            cid[q.conditions[0].condition_id] = i
        for i in res["Achieve"]["achieve"]["datas"]:
            if i.get("i_d", 0) in cid.keys():
                if params in i.get("param", ()):
                    rsp1 = make_QuestNotice(session, [i["i_d"]])
                    if rsp1:
                        session.send(MsgId.QuestNotice, rsp1, 0)
