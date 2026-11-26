"""角色/装备成长的共享校验与事务边界。

所有会同时改动角色或实例与材料的操作都必须持有玩家物品锁和数据库事务。
配置错误和状态错误在扣料前抛出；任何后续写库异常由最外层事务回滚。
"""

from contextlib import contextmanager

from proto.net_pb2 import Character, ItemDetail, StatusCode
import utils.db as db
from utils import item_mgr
from utils.res_loader import res


class GrowthError(Exception):
    def __init__(self, status):
        super().__init__(StatusCode.Name(status))
        self.status = status


@contextmanager
def transaction(player_id):
    # item_mgr 使用 RLock；db.transaction 使用全局 RLock 并支持最外层提交/回滚。
    with item_mgr.player_lock(player_id), db.transaction():
        yield


def rows(name, section):
    table = res.get(name, {})
    section = table.get(section, {}) if isinstance(table, dict) else {}
    data = section.get("datas", ()) if isinstance(section, dict) else ()
    return tuple(row for row in data if isinstance(row, dict))


def item_config(item_id):
    if not isinstance(item_id, int) or item_id <= 0:
        return None
    return next((row for row in rows("Item", "item") if row.get("i_d") == item_id), None)


def character_config(character_id):
    return next(
        (row for row in rows("Character", "character") if row.get("i_d") == character_id),
        None,
    )


def load_character(player_id, character_id):
    if not character_id:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    blobs = db.get_characters(player_id, character_id)
    if not blobs:
        raise GrowthError(StatusCode.StatusCode_CharNotExist)
    character = Character()
    try:
        character.ParseFromString(blobs[0])
    except Exception as error:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ) from error
    if character.character_id != character_id or character_config(character_id) is None:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    return character


def save_character(player_id, character):
    db.set_character(player_id, character.character_id, character.SerializeToString())


def normalize_costs(costs):
    """合并并校验材料；空列表表示配置明确的免费操作。"""
    merged = {}
    for cost in costs:
        if not isinstance(cost, (tuple, list)) or len(cost) != 2:
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        item_id, count = cost
        if (
            not isinstance(item_id, int)
            or item_id <= 0
            or not isinstance(count, int)
            or count <= 0
            or count > 0x7FFFFFFFFFFFFFFF
        ):
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        cfg = item_config(item_id)
        if cfg is None or cfg.get("new_bag_item_tag") in (2, 3, 5, 7, 34, 56):
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        merged[item_id] = merged.get(item_id, 0) + count
        if merged[item_id] > 0x7FFFFFFFFFFFFFFF:
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    return tuple(merged.items())


def configured_costs(entries, item_key, count_key):
    if not isinstance(entries, (tuple, list)):
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    costs = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        costs.append((entry.get(item_key, 0), entry.get(count_key, 0)))
    return normalize_costs(costs)


def consume(player_id, costs, pack_notice=None):
    costs = normalize_costs(costs)
    if costs and not item_mgr.consume_items(
        player_id, costs, pack_notice=pack_notice, session=None
    ):
        raise GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
    return costs


def load_owned_instance(player_id, instance_id, kind):
    """读取属于该玩家的装备/宠物实例，并校验内外层 ID 与资源配置。"""
    if not instance_id or kind not in ("weapon", "armor", "poster", "pet"):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    blob = db.get_item_detail(player_id, None, instance_id)
    if not isinstance(blob, (bytes, bytearray)):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    detail = ItemDetail()
    try:
        detail.ParseFromString(blob)
    except Exception as error:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ) from error
    if detail.main_item.WhichOneof("item") != kind:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    instance = getattr(detail.main_item, kind)
    item_id = detail.main_item.item_id
    if (
        not item_id
        or instance.instance_id != instance_id
        or getattr(instance, f"{kind}_id", getattr(instance, "item_id", 0)) != item_id
        or item_config(item_id) is None
    ):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    return detail


def equipment_group(kind, instance):
    """解析装备属性组，拒绝越界 property_index 与等级不匹配的损坏实例。"""
    if kind not in ("weapon", "armor"):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    table = res.get(kind.capitalize(), {})
    item_id = getattr(instance, f"{kind}_id", 0)
    cfg = next(
        (
            row
            for row in rows(kind.capitalize(), kind)
            if row.get("i_d") == item_id or row.get("item_i_d") == item_id
        ),
        None,
    )
    if cfg is None:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    prop_id = cfg.get(f"{kind}_property_i_d", 0)
    prop = next(
        (row for row in rows(kind.capitalize(), f"{kind}_property") if row.get("i_d") == prop_id),
        None,
    )
    groups = prop.get(f"{kind}_property_group_info", ()) if prop else ()
    if not isinstance(groups, (tuple, list)) or not groups:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    index = int(instance.property_index or 0)
    if 1 <= index <= len(groups):
        group = groups[index - 1]
    elif index == 0:
        # 兼容没有 property_index 的旧实例，但仍必须由等级唯一确定属性组。
        matches = [
            candidate
            for candidate in groups
            if isinstance(candidate, dict)
            and int(candidate.get("min_level", 0)) <= instance.level
            and (
                not candidate.get("max_level")
                or instance.level <= int(candidate["max_level"])
            )
        ]
        if len(matches) != 1:
            raise GrowthError(StatusCode.StatusCode_BAD_REQ)
        group = matches[0]
    else:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    if not isinstance(group, dict):
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    if instance.level < int(group.get("min_level", 0)) or (
        group.get("max_level") and instance.level > int(group["max_level"])
    ):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    return cfg, group


def strengthen_entry(kind, instance):
    _, group = equipment_group(kind, instance)
    strengthen_id = group.get("strengthen_i_d", 0)
    target = int(instance.strength_level or 0) + 1
    if not strengthen_id:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    group_row = next(
        (
            row
            for row in rows(kind.capitalize(), f"{kind}_strengthen")
            if row.get("i_d") == strengthen_id
        ),
        None,
    )
    entries = group_row.get(f"{kind}_strengthen_group_info", ()) if group_row else ()
    entry = next(
        (row for row in entries if isinstance(row, dict) and row.get("level") == target),
        None,
    )
    if entry is None:
        if kind == "weapon":
            status = StatusCode.StatusCode_WEAPON_MAX_STRENGTH_LEVEL
        else:
            status = StatusCode.StatusCode_ARMOR_MAX_STRENGTH_LEVEL
        raise GrowthError(status)
    costs = configured_costs(
        entry.get(f"{kind}_strength_need_item", ()),
        "need_item_i_d",
        "need_item_count",
    )
    return target, costs


def disassemble_row(kind, instance):
    _, group = equipment_group(kind, instance)
    disassemble_id = group.get("disassemble_i_d", 0)
    if not disassemble_id:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    row = next(
        (
            candidate
            for candidate in rows(kind.capitalize(), f"{kind}_disassemble")
            if candidate.get("i_d") == disassemble_id
        ),
        None,
    )
    if row is None:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    return row


def level_curve(character):
    cfg = character_config(character.character_id)
    growth_id = cfg.get("growth_level_i_d", 0) if cfg else 0
    level_cfg = next(
        (row for row in rows("Character", "level") if row.get("i_d") == growth_id),
        None,
    )
    infos = level_cfg.get("level_info", ()) if level_cfg else ()
    curve = {}
    for info in infos:
        if not isinstance(info, dict):
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        level = int(info.get("level", info.get("character_id", 0)) or 0)
        need = int(info.get("need_exp", 0) or 0)
        if level <= 0 or need <= 0 or level in curve:
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        curve[level] = (need, int(info.get("need_player_level", 1) or 1))
    if not curve:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    return curve


def plan_level_up(character, nums, player_level, energy_items):
    """在事务内读取最新角色/玩家等级后计算；超上限或跨玩家等级门槛整单拒绝。"""
    if len(nums) > len(energy_items) or any(int(num or 0) < 0 for num in nums):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    quantities = list(nums) + [0] * (len(energy_items) - len(nums))
    if not any(int(num or 0) > 0 for num in quantities):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    if (
        not 1 <= character.level <= character.max_level
        or character.max_level <= 0
        or character.max_level > 100
        or player_level <= 0
    ):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    curve = level_curve(character)
    if character.level < character.max_level:
        current_need = curve.get(character.level)
        if current_need is None or character.exp >= current_need[0]:
            raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    elif character.exp:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)

    costs = []
    total_exp = 0
    for item_id, raw_num in zip(energy_items, quantities):
        num = int(raw_num or 0)
        if num <= 0:
            continue
        cfg = item_config(item_id)
        exp_per_item = int(cfg.get("relate_i_d", 0) or 0) if cfg else 0
        if cfg is None or cfg.get("new_bag_item_tag") != 19 or exp_per_item <= 0:
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        if num > 0x7FFFFFFFFFFFFFFF // exp_per_item:
            raise GrowthError(StatusCode.StatusCode_BAD_REQ)
        costs.append((item_id, num))
        total_exp += num * exp_per_item
    costs = normalize_costs(costs)

    new_level = character.level
    new_exp = character.exp + total_exp
    blocked = False
    while new_level < character.max_level:
        need, required_player_level = curve.get(new_level, (0, 1))
        if not need:
            raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
        if player_level < required_player_level:
            blocked = True
            break
        if new_exp < need:
            break
        new_exp -= need
        new_level += 1
    if (blocked and new_exp >= need) or (new_level >= character.max_level and new_exp > 0):
        # 不静默吞掉超出玩家等级门槛的经验材料。
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    if new_level >= character.max_level:
        new_exp = 0
    if new_exp > 0xFFFFFFFF or (new_level, new_exp) == (character.level, character.exp):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    return costs, new_level, new_exp


def break_stage(character):
    rule = next(
        (row for row in rows("Character", "level_rule") if row.get("i_d") == character.character_id),
        None,
    )
    stages = rule.get("level_rule_info", ()) if rule else ()
    stage = next(
        (
            row
            for row in stages
            if isinstance(row, dict)
            and row.get("top_level") == character.max_level
            and int(row.get("top_max_level", 0) or 0) > character.max_level
        ),
        None,
    )
    if stage is None:
        raise GrowthError(StatusCode.StatusCode_CharacterSkillLvIsMax)
    if character.level < int(stage["top_level"]):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    next_max = int(stage["top_max_level"])
    if next_max > 100:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    costs = configured_costs(stage.get("rule_need_item", ()), "need_item_i_d", "need_item_count")
    return next_max, costs


def star_stage(character):
    cfg = next(
        (
            row
            for row in rows("Character", "character_star")
            if row.get("i_d") == character.character_id
        ),
        None,
    )
    infos = cfg.get("star_info", ()) if cfg else ()
    if not isinstance(infos, (tuple, list)) or not infos:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    max_star = max(int(info.get("star", 0) or 0) for info in infos if isinstance(info, dict))
    if not 0 <= character.star <= max_star:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    stage = next(
        (
            info
            for info in infos
            if isinstance(info, dict) and info.get("star") == character.star + 1
        ),
        None,
    )
    return stage, max_star


def skill_upgrade(skill_id, current_level):
    spell = next(
        (row for row in rows("Spell", "spell_info") if row.get("i_d") == skill_id),
        None,
    )
    levels = spell.get("spell_configure_items", ()) if spell else ()
    target = next(
        (
            row
            for row in levels
            if isinstance(row, dict) and row.get("level") == current_level + 1
        ),
        None,
    )
    if target is None:
        if current_level < 1:
            raise GrowthError(StatusCode.StatusCode_BAD_REQ)
        raise GrowthError(StatusCode.StatusCode_FAIL)
    cost_id = int(target.get("cost_i_d", 0) or 0)
    if not cost_id:
        return [], current_level + 1
    cost_cfg = next(
        (row for row in rows("Spell", "spell_level_up_info") if row.get("i_d") == cost_id),
        None,
    )
    groups = cost_cfg.get("spell_level_up_info_item", ()) if cost_cfg else ()
    if not groups:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    group = groups[0]
    ids = group.get("item_i_d", ())
    nums = group.get("num", ())
    if len(ids) != len(nums):
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    return normalize_costs(zip(ids, nums)), current_level + 1


def poster_max_star(poster_id):
    cfg = next(
        (row for row in rows("Poster", "poster") if row.get("i_d") == poster_id),
        None,
    )
    prop_id = cfg.get("property_i_d", 0) if cfg else 0
    prop = next(
        (row for row in rows("Poster", "poster_property") if row.get("i_d") == prop_id),
        None,
    )
    stars = [
        int(group.get("star", 0) or 0)
        for group in (prop.get("poster_property_group_info", ()) if prop else ())
        if isinstance(group, dict)
    ]
    if not stars or min(stars) <= 0:
        raise GrowthError(StatusCode.StatusCode_CFG_NOT_FOUND)
    return max(stars)


def load_owned_outfit(player_id, outfit_id):
    if not outfit_id or item_config(outfit_id) is None:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    if item_config(outfit_id).get("new_bag_item_tag") != 21:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    blob = db.get_item_detail(player_id, outfit_id)
    if not isinstance(blob, (bytes, bytearray)):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    detail = ItemDetail()
    try:
        detail.ParseFromString(blob)
    except Exception as error:
        raise GrowthError(StatusCode.StatusCode_BAD_REQ) from error
    if (
        detail.main_item.WhichOneof("item") != "outfit"
        or detail.main_item.item_id != outfit_id
        or detail.main_item.outfit.outfit_id != outfit_id
    ):
        raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    return detail


def validate_outfit_preset(player_id, preset):
    """校验时装槽位、物品归属和已解锁染色方案索引。"""
    slots = (
        "hat",
        "hair",
        "clothes",
        "ornament",
        "pend_top",
        "pend_chest",
        "pend_pelvis",
        "pend_up_face",
        "pend_down_face",
        "pend_left_hand",
        "pend_right_hand",
        "pend_left_foot",
        "pend_right_foot",
    )
    for slot in slots:
        item_id = int(getattr(preset, slot, 0) or 0)
        if not item_id:
            continue
        detail = load_owned_outfit(player_id, item_id)
        index = int(getattr(preset, f"{slot}_dye_scheme_index", 0) or 0)
        if index < 0:
            raise GrowthError(StatusCode.StatusCode_BAD_REQ)
        schemes = detail.main_item.outfit.dye_schemes
        if index >= len(schemes) or (schemes and not schemes[index].is_un_lock):
            raise GrowthError(StatusCode.StatusCode_BAD_REQ)
    for slot in slots:
        if not int(getattr(preset, slot, 0) or 0) and int(
            getattr(preset, f"{slot}_dye_scheme_index", 0) or 0
        ):
            raise GrowthError(StatusCode.StatusCode_BAD_REQ)
