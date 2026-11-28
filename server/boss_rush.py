import json
import threading
import time
import uuid
from datetime import datetime

from proto.net_pb2 import BossRushInfo, BossRushStageBattleInfo, MonsterInfo
from utils.res_loader import res
import utils.db as db


lock = threading.RLock()
_RUN_NAMESPACE = "boss_rush"
_RUN_VERSION = 1


def season(season_id):
    return next(
        (
            row
            for row in res.get("BossRush", {}).get("boss_rush_season", {}).get("datas", ())
            if row.get("i_d") == season_id
        ),
        None,
    )


def current_season(now=None):
    now = int(time.time() if now is None else now)
    for row in res.get("BossRush", {}).get("boss_rush_season", {}).get("datas", ()):
        if season_active(row, now):
            return row
    return None


def stage_group(season_data):
    if not season_data:
        return None
    stage_id = season_data.get("season_stage", season_data["i_d"])
    return next(
        (
            row
            for row in res.get("BossRush", {}).get("boss_rush_stage", {}).get("datas", ())
            if row.get("i_d") == stage_id
        ),
        None,
    )


def stage_rows(season_data):
    group = stage_group(season_data)
    return list(group.get("boss_rush_stage_group_info", ()) or ()) if group else []


def stage_config(season_data, stage_index):
    if not isinstance(stage_index, int) or isinstance(stage_index, bool):
        return None
    rows = stage_rows(season_data)
    return rows[stage_index] if 0 <= stage_index < len(rows) else None


def parse_time(value):
    if not value:
        return 0
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)


def season_active(season_data, now=None):
    if not season_data:
        return False
    now = int(time.time() if now is None else now)
    start = parse_time(season_data.get("start_time")) // 1000
    end = parse_time(season_data.get("end_time")) // 1000
    return bool(start and end and start <= now <= end)


def stage_unlocked(season_data, stage_index, now=None):
    stage = stage_config(season_data, stage_index)
    if not stage or not season_active(season_data, now):
        return False
    now = int(time.time() if now is None else now)
    start = parse_time(season_data.get("start_time")) // 1000
    begin_day = max(1, int(stage.get("begin_day", 1) or 1))
    return (now - start) // 86400 + 1 >= begin_day


def ensure_info(info, season_data):
    info.season_id = season_data["i_d"]
    info.start_time = parse_time(season_data.get("start_time"))
    info.end_time = parse_time(season_data.get("end_time"))
    info.show_rank_time = parse_time(season_data.get("show_rank_time"))
    expected = len(stage_rows(season_data))
    while len(info.stage_infos) < expected:
        info.stage_infos.add().stage_index = len(info.stage_infos)
    while len(info.stage_infos) > expected:
        del info.stage_infos[-1]
    for index, stage in enumerate(info.stage_infos):
        stage.stage_index = index
    info.best_total_score = sum(stage.best_score for stage in info.stage_infos)
    return info


def new_info(season_data):
    info = ensure_info(BossRushInfo(), season_data)
    info.current_stage_index = -1
    return info


def settle(info):
    """结束一轮挑战；只结算累计值，重复调用不会重复加分。"""
    for stage in info.stage_infos:
        if stage.total_score > stage.best_score:
            stage.best_score = stage.total_score
        stage.total_score = 0
        stage.total_damage_hp = 0
        stage.total_consume_time = 0
        stage.teams.clear()
    info.best_total_score = sum(stage.best_score for stage in info.stage_infos)
    info.current_stage_index = -1
    info.challenge_end_time = 0
    info.used_characters.clear()


def challenge_active(info, now=None):
    now = int(time.time() if now is None else now)
    return bool(
        info.challenge_end_time > 0
        and 0 <= info.current_stage_index < len(info.stage_infos)
        and now < info.challenge_end_time
    )


def monster_hp(monster_id, level):
    character = next(
        (
            row
            for row in res.get("Monster", {}).get("monster_character_data", {}).get("datas", ())
            if row.get("i_d") == monster_id
        ),
        None,
    )
    if not character:
        return 0
    growth = next(
        (
            row
            for row in res.get("Monster", {}).get("monster_growth_model", {}).get("datas", ())
            if row.get("i_d") == character.get("growth_model_i_d")
        ),
        None,
    )
    if not growth:
        return 0
    row = next(
        (item for item in growth.get("level_group_info", ()) if item.get("level") == level),
        None,
    )
    return int(row.get("max_h_p", 0) or 0) if row else 0


def dungeon_config(season_data, stage_index):
    stage = stage_config(season_data, stage_index)
    if not stage:
        return None
    return next(
        (
            row
            for row in res.get("Dungeon", {}).get("dungeon", {}).get("datas", ())
            if row.get("i_d") == stage.get("dungeon_i_d")
        ),
        None,
    )


def monster_snapshot(season_data, stage_index):
    dungeon = dungeon_config(season_data, stage_index)
    stage = stage_config(season_data, stage_index)
    if not dungeon or not stage or int(stage.get("max_h_p", 0) or 0) <= 0:
        return None
    monsters = []
    for monster_id in dungeon.get("monster_i_ds", ()) or ():
        hp = monster_hp(monster_id, int(dungeon.get("monster_lv", 1) or 1))
        if hp <= 0:
            return None
        monsters.append((int(monster_id), hp))
    return tuple(monsters) if monsters else None


def battle_info(season_data, stage_index):
    monsters = monster_snapshot(season_data, stage_index)
    dungeon = dungeon_config(season_data, stage_index)
    if monsters is None or not dungeon:
        return None
    result = BossRushStageBattleInfo(stage_index=stage_index, trigger_id=dungeon["i_d"])
    for monster_id, hp in monsters:
        result.monsters.add(monster_id=monster_id, remain_hp=hp)
    return result


def validate_battle_report(req, season_data, stage_index):
    """校验客户端战斗快照并计算伤害，不接受负数或额外/缺失怪物。"""
    if not req.HasField("battle_info"):
        return None
    report = req.battle_info
    dungeon = dungeon_config(season_data, stage_index)
    expected = monster_snapshot(season_data, stage_index)
    if not dungeon or expected is None:
        return None
    if report.stage_index != stage_index or report.trigger_id != dungeon["i_d"]:
        return None
    if len(report.monsters) != len(expected):
        return None
    damage = 0
    for monster, (monster_id, max_hp) in zip(report.monsters, expected):
        if monster.monster_id != monster_id or not 0 <= monster.remain_hp <= max_hp:
            return None
        damage += max_hp - int(monster.remain_hp)
    return damage


def max_attempts(dungeon):
    if not dungeon:
        return 0
    return max(1, int(dungeon.get("respawn_times", 0) or 0) + 1)


def run_key(season_id):
    return f"{season_id}:run"


def _decode_run(raw, season_id):
    if not raw:
        return None
    try:
        run = json.loads(raw)
        if (
            not isinstance(run, dict)
            or run.get("version") != _RUN_VERSION
            or run.get("season_id") != season_id
            or not run.get("run_id")
            or run.get("status") not in ("active", "entered", "battle", "settled", "expired")
        ):
            return None
        return run
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def load_run(player_id, season_id):
    return _decode_run(db.get_kv(player_id, _RUN_NAMESPACE, run_key(season_id)), season_id)


def save_run(player_id, season_id, run):
    db.set_kv(
        player_id,
        _RUN_NAMESPACE,
        run_key(season_id),
        json.dumps(run, sort_keys=True).encode("utf-8"),
    )


def new_run(season_id, stage_index, now_ms, end_time_ms):
    return {
        "version": _RUN_VERSION,
        "run_id": uuid.uuid4().hex,
        "season_id": season_id,
        "stage_index": stage_index,
        "status": "active",
        "start_time_ms": now_ms,
        "end_time_ms": end_time_ms,
        "team": [],
        "team_index": -1,
        "battle_start_ms": 0,
        "battle_end_ms": 0,
        "damage": 0,
        "elapsed_ms": 0,
        "settled_at_ms": 0,
    }


def run_active(run, now_ms=None):
    if not run or run.get("status") not in ("active", "entered", "battle"):
        return False
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    return now_ms < int(run.get("end_time_ms", 0) or 0)


def load_state(player_id, season_data, now=None):
    """读取并规范化持久状态；过期结算由调用方在事务中保存。"""
    now = int(time.time() if now is None else now)
    info = BossRushInfo()
    blob = db.get_boss_rush_info(player_id, season_data["i_d"])
    if blob:
        info.ParseFromString(blob)
    else:
        info.current_stage_index = -1
    ensure_info(info, season_data)
    run = load_run(player_id, season_data["i_d"])
    dirty = False
    now_ms = now * 1000
    if run and not run_active(run, now_ms) and run.get("status") in ("active", "entered", "battle"):
        run["status"] = "expired"
        run["settled_at_ms"] = now_ms
        settle(info)
        dirty = True
    elif info.challenge_end_time and (
        now >= info.challenge_end_time or info.current_stage_index < 0
    ):
        # 兼容旧版本只有 BossRushInfo、没有 run 记录的状态。
        settle(info)
        dirty = True
    elif not run and info.current_stage_index >= 0 and info.challenge_end_time:
        # 缺少 run 的旧进行中状态无法证明合法性，保守结束，不继续累计。
        settle(info)
        dirty = True
    return info, run, dirty


def save_state(player_id, season_id, info, run):
    db.set_boss_rush_info(player_id, season_id, info.SerializeToString())
    if run is not None:
        save_run(player_id, season_id, run)
