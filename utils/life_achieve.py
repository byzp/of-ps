"""生活成就进度 (GetLifeInfo/GetLifeAchieve/LifeAchieveNotice 共用口径)

官方抓包实锤 (pack0/1772954291.962684, 烹饪熟练度200 的账号):
条目 = 等级表条件成就 + 道具成就族(如 150130141~144), **count 取 achieve
存储的真实计数**(100110101 count:1, 与熟练度无关), 零计数条目不下发。
熟练度变动处(烹饪/钓鱼/制作/手工艺/缝纫成功后)调用 notify() 推送。
"""

from config import Config
from utils import achieve_track
from utils import refresh

import utils.db as db
from network.msg_id import MsgId
from proto.net_pb2 import (
    Achieve,
    LifeAchieve,
    LifeAchieveNotice,
    LifeBaseInfo,
    LifeType,
    StatusCode,
)
from utils.res_loader import res


def conditions_of(life_type):
    """该生活类型的成就条件 [(achieve_condition_i_d, 需要熟练度), ...]"""
    cfg = Config.LIFE_ACHIEVE_LIFE_TABLES.get(life_type)
    if not cfg:
        return []
    sheet, level_sheet, quest_key = cfg
    out = []
    for entry in res.get(sheet, {}).get(level_sheet, {}).get("datas", ()) or ():
        for info in entry.get(quest_key, ()) or ():
            out.append(
                (
                    info.get("achieve_condition_i_d"),
                    int(info.get("proficiency", 0) or 0),
                )
            )
    return out


def item_family_conditions(life_type):
    """道具成就族条件 achieve_condition_i_d 集合(如烹饪菜品 150130141~)"""
    cfg = Config.LIFE_ACHIEVE_LIFE_ITEM_FAMILIES.get(life_type)
    if not cfg:
        return ()
    sheet, sub, key = cfg
    rows = res.get(sheet, {}).get(sub, {}).get("datas", ()) or ()
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for e in row.get(key, ()) or ():
            if isinstance(e, dict) and e.get("achieve_condition_i_d"):
                out.append(e["achieve_condition_i_d"])
    return out


def progress_entries(player_id, life_type):
    """官方口径条目列表 [(achieve_id, 真实计数)]: 等级表条件成就 +
    道具成就族, count 一律取 achieve 存储, 零计数不下发。"""

    ids = {aid for aid, _need in conditions_of(life_type) if aid}
    ids.update(item_family_conditions(life_type))
    out = []
    for aid in sorted(ids):
        cur = achieve_track.progress(player_id, aid)
        if cur > 0:
            out.append((aid, cur))
    return out


def proficiency_of(player_id, life_type):
    """当前熟练度(无记录返回 0)"""
    blob = db.get_life(player_id, life_type)
    if not blob or not isinstance(blob, (bytes, bytearray)):
        return 0
    info = LifeBaseInfo()
    info.ParseFromString(blob)
    return int(info.proficiency_value)


def proficiency_conditions(life_type, level):
    """当前生活等级对应的熟练度条件及每日完成上限。"""
    cfg = Config.LIFE_ACHIEVE_LIFE_TABLES.get(life_type)
    if not cfg:
        return ()
    sheet, level_sheet, quest_key = cfg
    row = next(
        (r for r in res[sheet][level_sheet]["datas"] if r.get("i_d") == level), None
    )
    return row.get(quest_key, ()) if row else ()


def proficiency_gain(player_id, conditions, previous):
    """按通用累计次数计算本次熟练度，仅保存每日计数基线用于限制每日奖励。"""
    day = refresh.day_index()
    gain = 0
    for entry in conditions:
        aid = entry["achieve_condition_i_d"]
        before = previous[aid]
        after = achieve_track.progress(player_id, aid)
        key = f"{day}:{aid}"
        baseline = db.get_kv(player_id, "life_proficiency_base", key)
        if baseline is None:
            baseline = before
            db.set_kv(player_id, "life_proficiency_base", key, baseline)
        target = achieve_track.target_of(aid) or 1
        before, after = (
            max(0, before - int(baseline)) // target,
            max(0, after - int(baseline)) // target,
        )
        limit = entry.get("complete_limit", 0)
        if limit:
            before, after = min(before, limit), min(after, limit)
        gain += max(0, after - before) * entry.get("proficiency", 0)
    return gain


def build_notice(player_id, life_type, status=StatusCode.StatusCode_OK):
    """构造单个生活类型的 LifeAchieveNotice(真实 achieve 计数口径)"""
    n = LifeAchieveNotice()
    n.status = status
    la = n.life_achieves.add()
    la.life_type = life_type
    for ach_id, cur in progress_entries(player_id, life_type):
        a = la.life_achieve_.add()
        a.achieve_id = ach_id
        a.count = cur
    return n


def notify(session, life_type):
    """推送生活成就进度变动; 失败不影响主流程"""
    session.send(MsgId.LifeAchieveNotice, build_notice(session.player_id, life_type), 0)
