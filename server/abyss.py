"""Abyss configuration lookup, team validation, and persistent season summaries."""

from datetime import datetime
import threading
import time

from proto.net_pb2 import Character, DungeonData, StatusCode
from utils.algo import char_pack, char_unpack
import utils.db as db
from utils.res_loader import res


lock = threading.RLock()
PERMANENT_SEASON_ID = 9000001


def _rows(sheet, table):
    section = res.get(sheet, {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def parse_time(value):
    if not value:
        return 0
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timestamp())


def season(season_id):
    return next((row for row in _rows("Abyss", "abyss_season") if row.get("i_d") == season_id), None)


def permanent_season():
    return season(PERMANENT_SEASON_ID)


def season_active(season_data, now=None):
    if not season_data:
        return False
    if season_data.get("i_d") == PERMANENT_SEASON_ID:
        return True
    now = int(time.time() if now is None else now)
    start = parse_time(season_data.get("start_time"))
    end = parse_time(season_data.get("end_time"))
    return bool(start and end and start <= now <= end)


def current_season(now=None):
    return next((row for row in _rows("Abyss", "abyss_season") if season_active(row, now)), None)


def visible_seasons(now=None):
    permanent = permanent_season()
    return ([permanent] if permanent else []) + [
        row for row in _rows("Abyss", "abyss_season") if row.get("i_d") != PERMANENT_SEASON_ID and season_active(row, now)
    ]


def stage(season_data):
    if not season_data:
        return None
    stage_id = season_data.get("season_stage")
    return next((row for row in _rows("Abyss", "abyss_stage") if row.get("i_d") == stage_id), None)


def stage_rows(season_data):
    group = stage(season_data)
    return list(group.get("abyss_stage_group_info", ()) or ()) if group else []


def stage_entry(season_data, dungeon_id):
    return next((row for row in stage_rows(season_data) if row.get("dungeon_i_d") == dungeon_id), None)


def dungeon(dungeon_id):
    return next((row for row in _rows("Dungeon", "dungeon") if row.get("i_d") == dungeon_id), None)


def load_dungeon(player_id, dungeon_id):
    blob = db.get_dungeon(player_id, dungeon_id)
    if isinstance(blob, dict) or not blob:
        return None
    data = DungeonData()
    data.ParseFromString(blob)
    if data.dungeon_id != dungeon_id:
        return None
    return data


def team_members(team):
    return [int(getattr(team, name, 0) or 0) for name in ("char1", "char2", "char3")]


def stored_teams(data):
    return tuple(
        [char_unpack(getattr(data, name))[index] for name in ("char1", "char2", "char3")]
        for index in (0, 1)
    )


def validate_team(player_id, season_data, dungeon_id, team_index, members):
    if not season_active(season_data):
        return None, None, StatusCode.StatusCode_BAD_REQ
    entry = stage_entry(season_data, dungeon_id)
    config = dungeon(dungeon_id)
    if entry is None or config is None:
        return None, None, StatusCode.StatusCode_CFG_NOT_FOUND
    if team_index not in (0, 1) or (team_index == 1 and not entry.get("is_double_team")):
        return None, None, StatusCode.StatusCode_BAD_REQ
    level_row = db.get_players_info(player_id, "level")
    if not level_row or int(level_row[0]) < int(config.get("need_player_level", 1) or 1):
        return None, None, StatusCode.StatusCode_Lv_Not_Enough
    size = int(config.get("use_character_max_number", 3) or 0)
    if len(members) != 3 or size != 3:
        return None, None, StatusCode.StatusCode_DungeonTeamFull
    members = [int(member or 0) for member in members]
    if any(member <= 0 for member in members) or len(set(members)) != size:
        return None, None, StatusCode.StatusCode_DungeonTeamFull
    owned = set()
    for blob in db.get_characters(player_id):
        character = Character()
        character.ParseFromString(blob)
        owned.add(character.character_id)
    if not set(members).issubset(owned):
        return None, None, StatusCode.StatusCode_CharNotExist
    data = load_dungeon(player_id, dungeon_id)
    if data is not None and entry.get("is_double_team"):
        teams = stored_teams(data)
        other = 1 - team_index
        if any(member in teams[other] for member in members):
            return None, None, StatusCode.StatusCode_BAD_REQ
    return entry, config, None


def set_team(data, team_index, members):
    current = list(stored_teams(data))
    current[team_index] = [int(member or 0) for member in members]
    data.char1 = char_pack(current[0][0], current[1][0])
    data.char2 = char_pack(current[0][1], current[1][1])
    data.char3 = char_pack(current[0][2], current[1][2])


def stars(data, config):
    if data is None or config is None or int(data.finish_times or 0) <= 0 or int(data.last_finish_time or 0) <= 0:
        return 0
    elapsed = int(data.last_finish_time)
    result = 0
    for star in (1, 2, 3):
        timer = int(config.get(f"star_timer{star}", 0) or 0)
        if timer > 0 and elapsed <= timer * 1000:
            result = star
    return result


def season_summary(player_id, season_data):
    stored = db.get_dungeon(player_id)
    finished = total_time = total_stars = 0
    for entry in stage_rows(season_data):
        dungeon_id = entry.get("dungeon_i_d")
        config = dungeon(dungeon_id)
        blob = stored.get(dungeon_id) if isinstance(stored, dict) else None
        if not blob or config is None:
            continue
        data = DungeonData()
        data.ParseFromString(blob)
        if int(data.finish_times or 0) <= 0:
            continue
        finished += 1
        elapsed = int(data.last_finish_time or 0)
        total_time += elapsed
        total_stars += stars(data, config)
    return {"finished": finished, "total_time": total_time, "stars": total_stars}


def reward_config(season_data, achieve_id):
    if not season_data:
        return None
    table_id = season_data.get("season_achieve")
    table = next((row for row in _rows("Abyss", "season_achieve") if row.get("i_d") == table_id), None)
    if table is None:
        return None
    group = next((row for row in table.get("season_achieve_group_info", ()) if row.get("achieve_i_d") == achieve_id), None)
    return group.get("reward_i_d") if group else None


def achievement_met(player_id, season_data, achieve_id):
    row = next((item for item in _rows("Achieve", "achieve") if item.get("i_d") == achieve_id), None)
    if not row:
        return False
    condition = int(row.get("new_achieve_condition", 0) or 0)
    threshold = int(row.get("count_param", 0) or 0)
    summary = season_summary(player_id, season_data)
    if condition == 6:
        dungeon_id = int((row.get("param") or (0,))[0])
        data = load_dungeon(player_id, dungeon_id)
        return bool(stage_entry(season_data, dungeon_id) and data and data.finish_times > 0 and threshold <= 1)
    if condition == 58:
        return threshold > 0 and summary["stars"] >= threshold
    if condition == 59:
        return threshold > 0 and summary["finished"] >= threshold
    if condition == 60:
        params = row.get("param") or ()
        limit = int(params[0]) if params else 0
        return bool(limit > 0 and summary["finished"] > 0 and 0 < summary["total_time"] <= limit)
    return False
