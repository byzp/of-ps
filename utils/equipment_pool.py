"""随机掉落只使用配置、名称和图标完整的正式装备。"""

from functools import lru_cache

from config import Config
from utils.res_loader import res


@lru_cache(maxsize=1)
def random_equipment_ids():
    """返回可随机掉落的装备ID；UI.icon中的目录占位不代表有可用图标。"""
    weapons = {
        row["item_i_d"]
        for row in res["Weapon"]["weapon"]["datas"]
        if row.get("item_i_d") and row.get("new_weapon_system_type") in (1, 2, 3, 4, 5)
    }
    armors = {row["item_i_d"] for row in res["Armor"]["armor"]["datas"]}
    icons = {row["i_d"]: row for row in res["UI"]["icon"]["datas"]}
    texts = {
        row["i_d"]: row for row in res["String_Simplified"]["string_item_text"]["datas"]
    }
    eligible = set()
    for row in res["Item"]["item"]["datas"]:
        item_id = row["i_d"]
        tag = row.get("new_bag_item_tag")
        if tag == 2:
            if item_id not in weapons:
                continue
        elif tag == 3:
            if item_id not in armors:
                continue
        else:
            continue
        icon = icons.get(row.get("icon_i_d"))
        paths = icon.get("asset_full_name") if icon else None
        if not isinstance(paths, (list, tuple)) or not paths:
            continue
        if not all(
            isinstance(path, str)
            and path.strip()
            and not path.strip().endswith(("/", "\\"))
            for path in paths
        ):
            continue
        text = texts.get(row.get("text_i_d"))
        labels = text.get("text") if text else None
        if not isinstance(labels, (list, tuple)) or not labels:
            continue
        name = labels[0]
        if not isinstance(name, str) or not name.strip():
            continue
        if (
            name.strip()
            .casefold()
            .startswith(Config.RANDOM_EQUIPMENT_TEST_NAME_PREFIXES)
        ):
            continue
        eligible.add(item_id)
    return frozenset(eligible)
