"""副本持久进度；收集/击杀事实按点位去重，任务仍查询通用成就计数。"""

import threading

from proto.net_pb2 import DungeonData
from utils import achieve_track, db
from utils.res_loader import res

_locks = {}


def player_lock(player_id):
    """副本记录的读改写共用锁，防止结算/计时/击杀覆盖 finish_times。"""
    return _locks.setdefault(player_id, threading.RLock())


def load(player_id, dungeon_id):
    data = DungeonData(dungeon_id=dungeon_id)
    blob = db.get_dungeon(player_id, dungeon_id)
    if blob:
        data.ParseFromString(blob)
    return data


def task_ids(dungeon_id):
    config = next(
        (row for row in res["Dungeon"]["dungeon"]["datas"] if row["i_d"] == dungeon_id),
        None,
    )
    group_id = config.get("dengeon_quest_i_d") if config else None
    if not group_id:
        return []
    group = next(
        (
            row
            for row in res["Dungeon"]["dungeon_quest"]["datas"]
            if row["i_d"] == group_id
        ),
        None,
    )
    if not group:
        return []
    return [
        entry["achieve_condition_i_d"]
        for entry in group.get("dungeon_quest_group_info", ())
        if entry.get("achieve_condition_i_d")
    ]


def save(session, data):
    """包括未标 active 的资源收集任务；全任务完成以全部配置目标为准。"""
    ids = task_ids(data.dungeon_id)
    data.all_task_finished = bool(ids) and all(
        (target := achieve_track.target_of(aid)) is not None
        and achieve_track.progress(session.player_id, aid) >= target
        for aid in ids
    )
    db.set_dungeon(session.player_id, data.dungeon_id, data.SerializeToString())


def record_monster(session, monster_index, monster_id, monster_tag):
    """讨伐只计配置点位与怪物ID均匹配的击杀；场景怪物状态仍按索引保存。"""
    dungeon_id = session.dungeon[0]
    if not dungeon_id:
        return
    config = next(
        (
            row
            for row in res["ScenesConfigAsset"]["Dungeons"]
            if row["ID"] == dungeon_id
        ),
        None,
    )
    points = {
        (row["Index"], row["UnitID"])
        for row in (config.get("MonsterInfos", ()) if config else ())
    }
    task_monster = (monster_index, monster_id) in points
    data = load(session.player_id, dungeon_id)
    # 抓包包含任务表外的普通小怪索引0；它们保存场景状态，但不计讨伐目标。
    # 同索引的临时怪物不能提前标记该索引上配置的任务怪已被击败。
    if monster_index not in data.monsters and (
        task_monster or not any(index == monster_index for index, _ in points)
    ):
        data.monsters.append(monster_index)
    first_task_monster = task_monster and db.try_claim(
        session.player_id,
        "dungeon_monster_points",
        f"{dungeon_id}:{monster_index}:{monster_id}",
    )
    if monster_tag == 3 and not db.try_claim(
        session.player_id,
        "dungeon_boss_points",
        f"{dungeon_id}:{monster_index}:{monster_id}",
    ):
        monster_tag = None
    achieve_track.report(
        session,
        "dungeon_kill",
        dungeon_id=dungeon_id,
        monster_id=monster_id if first_task_monster else None,
        monster_tag=monster_tag,
    )
    save(session, data)
