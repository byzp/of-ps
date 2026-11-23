"""场景旗标配置关系。

Flag 的临时入口不是按 icon 全量展示，而是由已接取任务条件中的
Achieve.param 反查 Flag.flag_group_info.relation_i_d 得到。
"""

from utils.res_loader import res

_FLAG_ROWS = None
_ACHIEVE_INDEX = None
_DEFAULT_FLAG_IDS = None


def flag_rows():
    global _FLAG_ROWS
    if _FLAG_ROWS is None:
        table = res.get("Flag")
        table = table.get("flag") if isinstance(table, dict) else None
        rows = table.get("datas") if isinstance(table, dict) else None
        _FLAG_ROWS = (
            tuple(row for row in rows if isinstance(row, dict) and row.get("i_d"))
            if isinstance(rows, (list, tuple))
            else ()
        )
    return _FLAG_ROWS


def _manual_default_flag_ids():
    result = set()
    manual = res.get("Manual")
    if not isinstance(manual, dict):
        return result

    normal = manual.get("manual")
    normal = normal.get("datas") if isinstance(normal, dict) else None
    if isinstance(normal, (list, tuple)):
        for sheet in normal:
            if not isinstance(sheet, dict):
                continue
            for entry in sheet.get("manual_items") or ():
                if isinstance(entry, dict) and entry.get("flag_i_d"):
                    result.add(entry["flag_i_d"])

    dungeon = manual.get("manual_dungeon")
    dungeon = dungeon.get("datas") if isinstance(dungeon, dict) else None
    if isinstance(dungeon, (list, tuple)):
        for sheet in dungeon:
            if not isinstance(sheet, dict):
                continue
            for entry in sheet.get("manual_dungeon_items") or ():
                if not isinstance(entry, dict):
                    continue
                if entry.get("flag_i_d") and not entry.get("is_show_unlock"):
                    result.add(entry["flag_i_d"])
    return result


def is_default_flag(flag_id):
    """判断新号场景数据中无需任务触发即可展示的旗标。"""
    global _DEFAULT_FLAG_IDS
    if _DEFAULT_FLAG_IDS is None:
        _DEFAULT_FLAG_IDS = _manual_default_flag_ids()
    if flag_id in _DEFAULT_FLAG_IDS:
        return True

    row = next((item for item in flag_rows() if item.get("i_d") == flag_id), None)
    if not row:
        return False
    return row.get("icon_i_d") == 3 and flag_id != 10002


def _achieve_index():
    global _ACHIEVE_INDEX
    if _ACHIEVE_INDEX is None:
        table = res.get("Achieve")
        table = table.get("achieve") if isinstance(table, dict) else None
        rows = table.get("datas") if isinstance(table, dict) else None
        _ACHIEVE_INDEX = (
            {
                row["i_d"]: row
                for row in rows
                if isinstance(row, dict) and row.get("i_d")
            }
            if isinstance(rows, (list, tuple))
            else {}
        )
    return _ACHIEVE_INDEX


def flag_ids_for_conditions(condition_ids):
    """按任务条件成就的 param 反查可被任务激活的旗标。"""
    params = set()
    achieves = _achieve_index()
    for condition_id in condition_ids:
        achieve = achieves.get(condition_id)
        if not achieve:
            continue
        values = achieve.get("param")
        if not isinstance(values, (list, tuple)):
            continue
        params.update(values)

    result = []
    for row in flag_rows():
        if is_default_flag(row["i_d"]):
            continue
        for group in row.get("flag_group_info") or ():
            if not isinstance(group, dict):
                continue
            if group.get("relation_i_d") in params:
                result.append(row["i_d"])
                break
    return result


def flag_relations(flag_id):
    row = next((item for item in flag_rows() if item.get("i_d") == flag_id), None)
    if not row:
        return ()
    return tuple(
        group.get("relation_i_d")
        for group in row.get("flag_group_info") or ()
        if isinstance(group, dict) and group.get("relation_i_d")
    )
