"""活动奖励的窗口、条件、周期与原子领取服务。"""

import base64
from datetime import datetime
import json
import random
import time

from config import Config
from proto.net_pb2 import PackNotice, StatusCode
import utils.db as db
from utils import achieve_track, activity_state, item_mgr, refresh
from utils.res_loader import res

_OK = StatusCode.StatusCode_OK
_BAD_REQ = StatusCode.StatusCode_BAD_REQ
_CFG_NOT_FOUND = StatusCode.StatusCode_CFG_NOT_FOUND
_ACTIVITY_CLOSE = StatusCode.StatusCode_Activity_Close
_REPEAT = StatusCode.StatusCode_REPEAT_GET_REWARD
_NOT_FINISHED = StatusCode.StatusCode_NotFinishAllTask
_OPERATION_NS = "activity_operations"


def _rows(sheet, table):
    value = res.get(sheet, {})
    value = value.get(table, {}) if isinstance(value, dict) else {}
    rows = value.get("datas", ()) if isinstance(value, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def _parse_time(value):
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    except (TypeError, ValueError):
        return 0


def activity_instance(activity_id, expected_kind=None, now=None, allow_closed=False):
    """返回 (实例 id, 类型, 模板 id, 开始 ms, 结束 ms)，未知实例返回 None。"""
    now_ms = int((time.time() if now is None else now) * 1000)
    if activity_id in Config.INACTIVE_ACTIVITY_IDS:
        return None
    override = Config.ACTIVITY_INSTANCES.get(activity_id)
    if override:
        if activity_id not in Config.ACTIVITY_VISIBLE_IDS or len(override) != 4:
            return None
        kind, template, start, end = override
        start, end = int(start or 0), int(end or 0)
    else:
        if activity_id not in Config.ACTIVITY_VISIBLE_IDS:
            return None
        row = next((row for row in _rows("Activity", "activity") if row.get("i_d") == activity_id), None)
        if row is None:
            return None
        kind = int(row.get("new_activity_type", 0) or 0)
        template = row.get("activity_i_d", activity_id)
        start = _parse_time(row.get("opening_time"))
        end = _parse_time(row.get("closing_time"))
    if expected_kind is not None and int(kind) != int(expected_kind):
        return None
    if not allow_closed and (start > now_ms or (end and now_ms > end)):
        return None
    return int(activity_id), int(kind), template, start, end


def activity_status(activity_id, expected_kind=None, now=None):
    if activity_instance(activity_id, expected_kind, now, allow_closed=True) is None:
        return _CFG_NOT_FOUND
    if activity_instance(activity_id, expected_kind, now) is None:
        return _ACTIVITY_CLOSE
    return _OK


def activity_day(instance, player_id=None, now=None):
    """活动第几天；无开放时间的常驻活动沿用登录签到计数。"""
    start = instance[3]
    now = time.time() if now is None else now
    if start:
        return max(1, refresh.day_index(now) - refresh.day_index(start // 1000) + 1)
    if player_id is not None:
        return max(1, int(db.get_kv(player_id, "sign_in", f"{instance[0]}:days", 0) or 0))
    return 1


def _valid_rewards(rewards):
    if not rewards:
        return False
    return all(
        isinstance(entry, (list, tuple))
        and len(entry) == 2
        and int(entry[0]) > 0
        and int(entry[1]) > 0
        for entry in rewards
    )


def _resource_rewards(entries, item_key="item_i_d", num_key="item_num"):
    return [
        (int(entry[item_key]), int(entry[num_key]))
        for entry in entries or ()
        if entry.get(item_key) and int(entry.get(num_key, 0) or 0) > 0
    ]


def _condition_status(player_id, condition_id):
    target = achieve_track.target_of(condition_id)
    if target is None:
        return _CFG_NOT_FOUND
    if activity_state.condition_progress(player_id, condition_id) < int(target):
        return _NOT_FINISHED
    return _OK


def _item_count(player_id, item_id):
    raw = db.get_item_detail(player_id, item_id)
    if not raw:
        return 0
    from proto.net_pb2 import ItemDetail

    detail = ItemDetail()
    detail.ParseFromString(raw)
    return int(detail.main_item.base_item.num)


def _global_values(key):
    for row in _rows("GlobalConfig", "config"):
        if row.get("key") == key:
            values = row.get("values") or ()
            return values if isinstance(values, (list, tuple)) else ()
    return ()


def _global_numbers(key, expected):
    """GlobalConfig 既可能是分列值，也可能是 '102:50:1000' 单值。"""
    parts = []
    for value in _global_values(key):
        for part in str(value).split(":"):
            parts.append(part)
    if len(parts) != expected:
        return None
    try:
        return tuple(int(part) for part in parts)
    except (TypeError, ValueError):
        return None


def _sign_rewards(activity_id, day):
    template = activity_state.template_id(activity_id)
    for row in _rows("ActivitySign", "activity_sign"):
        if row.get("i_d") != template:
            continue
        for entry in row.get("activity_sign_item", ()):
            if int(entry.get("days", 0) or 0) == int(day):
                return _resource_rewards(entry.get("activity_sign_reward_item", ()))
        return None
    return None


def claim_sign_in(player_id, activity_id, day, rewards_out, pack, now=None):
    instance = activity_instance(activity_id, 1, now)
    if instance is None:
        return activity_status(activity_id, 1, now), 0
    rewards = _sign_rewards(activity_id, day)
    if not _valid_rewards(rewards):
        return _CFG_NOT_FOUND, 0
    current_day = activity_day(instance, player_id, now)
    if day < 1 or day > current_day:
        return _BAD_REQ, 0
    key = f"{activity_id}:{day}"
    with item_mgr.player_lock(player_id), db.transaction():
        if day > 1 and not db.has_claimed(player_id, "activity_sign", f"{activity_id}:{day - 1}"):
            return StatusCode.StatusCode_FAIL, 0
        if not db.try_claim(player_id, "activity_sign", key):
            return _REPEAT, _sign_bitmap(player_id, activity_id)
        item_mgr.grant_items(player_id, rewards, rsp_items=rewards_out, pack_notice=pack)
        bitmap = _sign_bitmap(player_id, activity_id)
    return _OK, bitmap


def _sign_bitmap(player_id, activity_id):
    bitmap = 0
    for key in db.get_claimed(player_id, "activity_sign"):
        parts = key.split(":")
        if len(parts) == 2 and parts[0] == str(activity_id) and parts[1].isdigit():
            day = int(parts[1])
            if 0 < day < 32:
                bitmap |= 1 << day
    return bitmap


def claim_activity_quest(player_id, activity_id, param, is_progress, rewards_out, pack, now=None):
    instance = activity_instance(activity_id, 0, now)
    if instance is None:
        return activity_status(activity_id, 0, now), []
    template = instance[2]
    row = next((row for row in _rows("ActivityQuest", "activity_quest") if row.get("i_d") == template), None)
    if row is None:
        return _CFG_NOT_FOUND, []
    if is_progress:
        return _claim_quest_progress(player_id, activity_id, param, row, rewards_out, pack)
    current_day = activity_day(instance, player_id, now)
    day_items = [item for item in row.get("activity_quest_achieve_items", ()) if int(item.get("days", 0) or 0) == param]
    if not day_items:
        return _CFG_NOT_FOUND, []
    if param < 1 or param > current_day:
        return _BAD_REQ, []
    configured = []
    for item in day_items:
        condition_id = int(item.get("achieve_i_d", 0) or 0)
        rewards = _resource_rewards(item.get("activity_quest_item", ()))
        if not condition_id or achieve_track.target_of(condition_id) is None:
            return _CFG_NOT_FOUND, []
        if not _valid_rewards(rewards):
            return _CFG_NOT_FOUND, []
        configured.append((condition_id, rewards))
    claimed = []
    totals = {}
    completed_any = False
    with item_mgr.player_lock(player_id), db.transaction():
        for condition_id, rewards in configured:
            if activity_state.condition_progress(player_id, condition_id) < int(achieve_track.target_of(condition_id)):
                continue
            completed_any = True
            key = f"{activity_id}:achieve:{condition_id}"
            if not db.try_claim(player_id, "activity_quest", key):
                continue
            claimed.append(condition_id)
            for item_id, count in rewards:
                totals[item_id] = totals.get(item_id, 0) + count
        if not claimed:
            return (_REPEAT if completed_any else _NOT_FINISHED), []
        item_mgr.grant_items(player_id, list(totals.items()), rsp_items=rewards_out, pack_notice=pack)
    return _OK, claimed


def _claim_quest_progress(player_id, activity_id, param, row, rewards_out, pack):
    reward_row = next(
        (entry for entry in _rows("ActivityQuest", "activity_quest_reward") if entry.get("i_d") == row.get("activity_quest_reward_i_d")),
        None,
    )
    tiers = list(reward_row.get("activity_quest_reward_item", ())) if reward_row else ()
    tier = next((entry for entry in tiers if int(entry.get("index", 0) or 0) == param), None)
    if tier is None:
        return _CFG_NOT_FOUND, []
    rewards = []
    reward_id = int(tier.get("reward_item_i_d", 0) or 0)
    reward_num = int(tier.get("reward_item_num", 0) or 0)
    if reward_id > 0 and reward_num > 0:
        rewards.append((reward_id, reward_num))
    if not _valid_rewards(rewards):
        return _CFG_NOT_FOUND, []
    key = f"{activity_id}:progress:{param}"
    with item_mgr.player_lock(player_id), db.transaction():
        previous = [int(entry.get("index", 0) or 0) for entry in tiers if int(entry.get("index", 0) or 0) < param]
        if previous and not db.has_claimed(player_id, "activity_quest", f"{activity_id}:progress:{max(previous)}"):
            return _NOT_FINISHED, []
        condition_item = int(tier.get("condition_item_i_d", 0) or 0)
        condition_num = int(tier.get("condition_item_num", 0) or 0)
        if not condition_item or condition_num <= 0:
            return _CFG_NOT_FOUND, []
        if _item_count(player_id, condition_item) < condition_num:
            return StatusCode.StatusCode_ITEM_NOT_ENOUGH, []
        if not db.try_claim(player_id, "activity_quest", key):
            return _REPEAT, []
        item_mgr.grant_items(player_id, rewards, rsp_items=rewards_out, pack_notice=pack)
    return _OK, []


def _regular_pool(activity_id, pool_type):
    template = activity_state.template_id(activity_id)
    row = next((row for row in _rows("ActivityRegular", "activity_regular") if row.get("i_d") == template), None)
    if row is None:
        return None
    if pool_type == 1:
        pool_id = row.get("daily_pool_i_d") or row.get("daily_refresh_pool_i_d")
    elif pool_type == 2:
        pool_id = row.get("random_pool_i_d")
    elif pool_type == 3:
        pool_id = row.get("pool_i_d")
    else:
        return None
    if not pool_id:
        return None
    return next((pool for pool in _rows("ActivityRegular", "activity_regular_pool") if pool.get("i_d") == pool_id), None)


def claim_regular_reward(player_id, activity_id, pool_type, param, rewards_out, pack, now=None):
    instance = activity_instance(activity_id, 4, now)
    if instance is None:
        return activity_status(activity_id, 4, now)
    if pool_type not in (1, 2, 3):
        return _BAD_REQ
    pool = _regular_pool(activity_id, pool_type)
    if pool is None:
        return _CFG_NOT_FOUND
    entry = next((entry for entry in pool.get("activity_regular_pool_item", ()) if int(entry.get("achieve_i_d", 0) or 0) == param), None)
    if entry is None:
        return _CFG_NOT_FOUND
    rewards = _resource_rewards(entry.get("activity_regular_pool_reward_item", ()))
    if not _valid_rewards(rewards) or achieve_track.target_of(param) is None:
        return _CFG_NOT_FOUND
    explicit_day = int(entry.get("days", 0) or 0)
    if explicit_day and explicit_day > activity_day(instance, player_id, now):
        return _BAD_REQ
    period = f":d{refresh.day_index(now)}" if pool_type == 1 and not explicit_day else ""
    key = f"{activity_id}:{pool_type}:{param}{period}"
    with item_mgr.player_lock(player_id), db.transaction():
        if explicit_day > 1:
            previous = next(
                (item for item in pool.get("activity_regular_pool_item", ()) if int(item.get("days", 0) or 0) == explicit_day - 1),
                None,
            )
            if previous and not db.has_claimed(player_id, "activity_regular", f"{activity_id}:{pool_type}:{previous['achieve_i_d']}"):
                return _NOT_FINISHED
        status = _condition_status(player_id, param)
        if status != _OK:
            return status
        if not db.try_claim(player_id, "activity_regular", key):
            return _REPEAT
        item_mgr.grant_items(player_id, rewards, rsp_items=rewards_out, pack_notice=pack)
    return _OK


def claim_gift_reward(player_id, activity_id, achieve_id, rewards_out, pack, now=None):
    instance = activity_instance(activity_id, 2, now)
    if instance is None:
        return activity_status(activity_id, 2, now)
    row = next((row for row in _rows("ActivityGift", "activity_gift") if row.get("i_d") == instance[2]), None)
    if row is None:
        return _CFG_NOT_FOUND
    entry = next((entry for entry in row.get("activity_gift_item", ()) if int(entry.get("achieve_i_d", 0) or 0) == achieve_id), None)
    if entry is None:
        return _CFG_NOT_FOUND
    rewards = _resource_rewards(entry.get("a_activity_gift_reward_item", ()))
    if not _valid_rewards(rewards):
        return _CFG_NOT_FOUND
    with item_mgr.player_lock(player_id), db.transaction():
        status = _condition_status(player_id, achieve_id)
        if status != _OK:
            return status
        if not db.try_claim(player_id, "activity_gift", f"{activity_id}:{achieve_id}"):
            return StatusCode.StatusCode_ActivityGift_Rewarded
        item_mgr.grant_items(player_id, rewards, rsp_items=rewards_out, pack_notice=pack)
    return _OK


def _battle_pass(activity_id, now=None):
    instance = activity_instance(activity_id, 3, now)
    if instance is None:
        return None, activity_status(activity_id, 3, now)
    row = next((row for row in _rows("BattlePass", "battle_pass") if row.get("i_d") == instance[2]), None)
    return (row, instance) if row else (None, _CFG_NOT_FOUND)


def _buy_exp_config():
    values = _global_numbers("BattlePass_BuyExp_Currency", 3)
    if values is None:
        return None
    currency_id, cost, exp = values
    return (currency_id, cost, exp) if currency_id > 0 and cost > 0 and exp > 0 else None


def buy_battle_pass_exp(player_id, activity_id, packet_id, response, pack, now=None):
    if packet_id <= 0:
        return _BAD_REQ, (0, 0, 0)
    bp, status = _battle_pass(activity_id, now)
    if bp is None:
        return status, (0, 0, 0)
    cost_config = _buy_exp_config()
    if cost_config is None:
        return _CFG_NOT_FOUND, (0, 0, 0)
    currency_id, cost, exp = cost_config
    fingerprint = json.dumps([int(activity_id)], separators=(",", ":"))
    with item_mgr.player_lock(player_id), db.transaction():
        operation = _load_operation(player_id, "battle-pass-buy-exp", activity_id, packet_id, fingerprint)
        if operation == "conflict":
            return _BAD_REQ, (0, 0, 0)
        if operation is not None:
            response.ParseFromString(operation[0])
            pack.ParseFromString(operation[1])
            return response.status, (response.battle_pass_lv, response.total_exp, response.current_exp)
        level, _, _ = db.bp_get_exp(player_id, activity_id)
        if level >= len(bp.get("battle_pass_level_ups", ())):
            return StatusCode.StatusCode_BattlePass_MaxLevel, (level, 0, 0)
        if not item_mgr.consume_items(player_id, [(currency_id, cost)], pack_notice=pack):
            return StatusCode.StatusCode_ITEM_NOT_ENOUGH, (level, 0, 0)
        result = db.bp_add_exp(player_id, activity_id, exp)
        response.status = _OK
        response.battle_pass_lv, response.total_exp, response.current_exp = result
        _save_operation(player_id, "battle-pass-buy-exp", activity_id, packet_id, fingerprint, response, pack)
    return _OK, result


def _bp_quest(bp, achieve_id):
    for field, period in (("day_quest_i_d", "d"), ("week_quest_i_d", "w"), ("season_quest_i_d", "s")):
        group_id = bp.get(field)
        group = next((group for group in _rows("BattlePass", "battle_pass_queset") if group.get("i_d") == group_id), None)
        if group is None:
            continue
        for entry in group.get("battle_pass_queset_item", ()):
            if int(entry.get("achieve_i_d", 0) or 0) == achieve_id:
                exp = int(entry.get("exp", 0) or 0)
                return (period, exp) if exp > 0 else None
    return None


def claim_battle_pass_quest(player_id, activity_id, achieve_id, now=None):
    bp, status = _battle_pass(activity_id, now)
    if bp is None:
        return status, (0, 0, 0, 0, 0)
    quest = _bp_quest(bp, achieve_id)
    if quest is None or achieve_track.target_of(achieve_id) is None:
        return _CFG_NOT_FOUND, (0, 0, 0, 0, 0)
    period, exp = quest
    token = ""
    if period == "d":
        token = f"d{refresh.day_index(now)}"
    elif period == "w":
        token = "w" + time.strftime("%G-W%V", time.localtime(time.time() if now is None else now))
    key = f"{activity_id}:{achieve_id}" + (f":{token}" if token else "")
    with item_mgr.player_lock(player_id), db.transaction():
        status = _condition_status(player_id, achieve_id)
        if status != _OK:
            return status, (0, 0, 0, 0, 0)
        if not db.try_claim(player_id, "bp_quest_reward", key):
            return StatusCode.StatusCode_BattlePass_QuestRewarded, (0, 0, 0, 0, 0)
        level, total, current = db.bp_add_exp(player_id, activity_id, exp)
        week = db.incr_kv(player_id, "battle_pass_week", "exp:" + token[1:], exp) if period == "w" else int(db.get_kv(player_id, "battle_pass_week", "exp:" + time.strftime("%G-W%V"), 0) or 0)
    return _OK, (exp, level, week, total, current)


def claim_battle_pass_level_reward(player_id, activity_id, level, is_free, rewards_out, pack, now=None):
    bp, status = _battle_pass(activity_id, now)
    if bp is None:
        return status
    level_row = next((row for row in bp.get("battle_pass_level_ups", ()) if int(row.get("level", 0) or 0) == level), None)
    if level_row is None or level < 1:
        return _CFG_NOT_FOUND
    reward_rows = level_row.get("battle_pass_reward", ())
    index = 0 if is_free else 1
    if index >= len(reward_rows):
        return _CFG_NOT_FOUND
    reward = reward_rows[index]
    reward_id = int(reward.get("item_i_d", 0) or 0)
    reward_num = int(reward.get("item_num", 0) or 0)
    rewards = [(reward_id, reward_num)] if reward_id > 0 and reward_num > 0 else []
    if not _valid_rewards(rewards):
        return _CFG_NOT_FOUND
    with item_mgr.player_lock(player_id), db.transaction():
        current_level, _, _ = db.bp_get_exp(player_id, activity_id)
        if current_level < level:
            return StatusCode.StatusCode_BattlePass_LevelLimit
        if not is_free and not db.get_kv(player_id, "activity_entitlements", f"battle_pass:{activity_id}"):
            return StatusCode.StatusCode_BattlePass_Not_Buy
        if not db.try_claim(player_id, "bp_level_reward", f"{activity_id}:{level}:{bool(is_free)}"):
            return StatusCode.StatusCode_BattlePass_LvRewarded
        item_mgr.grant_items(player_id, rewards, rsp_items=rewards_out, pack_notice=pack)
    return _OK


def _month_card_reward():
    values = _global_numbers("MoonCard_Rveryday_Currency", 2)
    if values is None:
        return None
    item_id, count = values
    return (item_id, count) if item_id > 0 and count > 0 else None


def _month_card_limit():
    values = _global_numbers("MoonCard_MaxRemainingDay", 1)
    if values is None:
        return 0
    return max(0, values[0])


def claim_month_card(player_id, rewards_out, pack, now=None):
    reward = _month_card_reward()
    if reward is None:
        return _CFG_NOT_FOUND, 0
    now = int(time.time() if now is None else now)
    day = str(refresh.day_index(now))
    with item_mgr.player_lock(player_id), db.transaction():
        overdue = int(db.get_month_card_over_due_time(player_id) or 0)
        reward_days = int(db.get_month_card_reward_days(player_id) or 0)
        if overdue <= now:
            return StatusCode.StatusCode_FAIL, reward_days
        limit = _month_card_limit()
        if (limit and reward_days >= limit) or not db.try_claim(player_id, "month_card", day):
            return StatusCode.StatusCode_MOON_CARD_DAYS_LIMIT, reward_days
        item_mgr.grant_items(player_id, [reward], rsp_items=rewards_out, pack_notice=pack)
        db.set_month_card_reward_days(player_id, reward_days + 1)
        reward_days += 1
    return _OK, reward_days


def _operation_key(system, activity_id, packet_id):
    return f"{system}:{activity_id}:{packet_id}"


def _load_operation(player_id, system, activity_id, packet_id, fingerprint):
    raw = db.get_kv(player_id, _OPERATION_NS, _operation_key(system, activity_id, packet_id))
    if raw is None:
        return None
    try:
        stored = json.loads(bytes(raw).decode("utf-8"))
        if stored.get("fingerprint") != fingerprint:
            return "conflict"
        return base64.b64decode(stored["response"]), base64.b64decode(stored["pack"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError):
        return "conflict"


def _save_operation(player_id, system, activity_id, packet_id, fingerprint, response, pack):
    if not packet_id:
        return
    value = json.dumps(
        {
            "fingerprint": fingerprint,
            "response": base64.b64encode(response.SerializeToString()).decode("ascii"),
            "pack": base64.b64encode(pack.SerializeToString()).decode("ascii"),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    db.set_kv(player_id, _OPERATION_NS, _operation_key(system, activity_id, packet_id), value)


def _turntable_config(activity_id):
    template = activity_state.template_id(activity_id)
    cfg = next((row for row in _rows("ActivityTurntable", "activity_turntable") if row.get("i_d") == template), None)
    if cfg is None:
        return None, []
    pool = next((row for row in _rows("ActivityTurntable", "turntable_pool") if row.get("i_d") == cfg.get("turntable_pool_i_d")), None)
    return cfg, list(pool.get("turntable_pool_item", ())) if pool else []


def _valid_turntable(cfg, items):
    if not cfg or not items:
        return False
    try:
        cost_item = int(cfg.get("cost_item_i_d", 0) or 0)
        first_cost = int(cfg.get("first_one_need_item_num", 0) or 0)
        cost = int(cfg.get("one_need_item_num", 0) or 0)
    except (TypeError, ValueError):
        return False
    if cost_item <= 0 or first_cost < 0 or cost <= 0:
        return False
    indexes = set()
    for entry in items:
        try:
            index = int(entry.get("index", 0) or 0)
            item_id = int(entry.get("item_i_d", 0) or 0)
            count = int(entry.get("item_num", 0) or 0)
            limit = int(entry.get("limit_num", 0) or 0)
            weight = int(entry.get("weight", 0) or 0)
        except (TypeError, ValueError):
            return False
        if index <= 0 or index in indexes or item_id <= 0 or count <= 0 or limit < 0 or weight < 0:
            return False
        indexes.add(index)
    return sum(max(0, int(entry.get("weight", 0) or 0)) for entry in items) > 0


def draw_turntable(player_id, activity_id, draw_times, packet_id, rsp, pack, now=None):
    """执行一次转盘；返回是否重放已提交的幂等响应。"""
    if packet_id <= 0:
        rsp.status = _BAD_REQ
        return False
    if draw_times <= 0 or draw_times > Config.TURNTABLE_MAX_DRAW_TIMES:
        rsp.status = _BAD_REQ
        return False
    fingerprint = json.dumps([int(activity_id), int(draw_times)], separators=(",", ":"))
    with item_mgr.player_lock(player_id), db.transaction():
        operation = _load_operation(player_id, "turntable", activity_id, packet_id, fingerprint)
        if operation == "conflict":
            rsp.status = _BAD_REQ
            return False
        if operation is not None:
            rsp.ParseFromString(operation[0])
            pack.ParseFromString(operation[1])
            return True
        if activity_instance(activity_id, 6, now) is None:
            rsp.status = activity_status(activity_id, 6, now)
            return False
        cfg, items = _turntable_config(activity_id)
        if not _valid_turntable(cfg, items):
            rsp.status = _CFG_NOT_FOUND
            return False
        used = db.get_turntable_used_counts(player_id, activity_id)
        first = not db.has_turntable_drawn(player_id, activity_id)
        plan = []
        for _ in range(draw_times):
            available = [
                entry for entry in items
                if not int(entry.get("limit_num", 0) or 0)
                or used.get(int(entry["index"]), 0) < int(entry["limit_num"])
            ]
            if not available:
                break
            hit = random.choices(available, weights=[int(entry.get("weight", 0) or 0) for entry in available], k=1)[0]
            index = int(hit["index"])
            used[index] = used.get(index, 0) + 1
            plan.append(hit)
        if len(plan) != draw_times:
            rsp.status = StatusCode.StatusCode_TURNTABLE_NO_REWARD_REMAIN
            return False
        first_cost = int(cfg.get("first_one_need_item_num", 0) or 0)
        one_cost = int(cfg.get("one_need_item_num", 0) or 0)
        total_cost = (first_cost if first else one_cost) + (len(plan) - 1) * one_cost
        if not item_mgr.consume_items(player_id, [(int(cfg["cost_item_i_d"]), total_cost)], pack_notice=pack):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            return False
        draw_time = int(time.time() if now is None else now)
        rewards = []
        for entry in plan:
            index = int(entry["index"])
            item_id, count = int(entry["item_i_d"]), int(entry["item_num"])
            rsp.reward_indexes.append(index)
            rewards.append((item_id, count))
            db.add_turntable_record(player_id, activity_id, index, item_id, count, draw_time)
        item_mgr.grant_items(player_id, rewards, rsp_items=rsp.rewards, pack_notice=pack)
        rsp.status = _OK
        _save_operation(player_id, "turntable", activity_id, packet_id, fingerprint, rsp, pack)
    return False


def _supply_interval_bounds():
    values = _global_numbers("SupplyBox_Random_Time", 2)
    if values is None:
        return None
    low, high = values
    return (low, high) if low > 0 and high > 0 else None


def _supply_interval_seconds():
    bounds = _supply_interval_bounds()
    if bounds is None:
        return None
    return random.randint(min(bounds), max(bounds)) * 60


def _supply_reward_options():
    """二项为等权奖励项；三项为 (weight, item_id, count)。"""
    options = []
    for entry in getattr(Config, "SUPPLY_BOX_REWARDS", ()) or ():
        if not isinstance(entry, (list, tuple)):
            return None
        if len(entry) == 2:
            weight, item_id, count = 1, entry[0], entry[1]
        elif len(entry) == 3:
            weight, item_id, count = entry
        else:
            return None
        try:
            weight, item_id, count = int(weight), int(item_id), int(count)
        except (TypeError, ValueError):
            return None
        if weight <= 0 or item_id <= 0 or count <= 0:
            return None
        options.append((weight, (item_id, count)))
    return options or None


def supply_next_reward_time(player_id, now=None):
    interval = _supply_interval_seconds()
    if interval is None:
        return None
    now = int(time.time() if now is None else now)
    with item_mgr.player_lock(player_id), db.transaction():
        value = db.get_kv(player_id, "player", "supply_box_next")
        if value is None:
            created = db.get_players_info(player_id, "create_time")
            base = int(created[0]) if created and created[0] else now
            value = base + interval
            db.set_kv(player_id, "player", "supply_box_next", value)
    return int(value)


def claim_supply_box(player_id, packet_id, rsp, pack, now=None):
    """补给箱冷却、随机、发奖和幂等记录在同一事务提交。"""
    options = _supply_reward_options()
    interval = _supply_interval_seconds()
    if options is None or interval is None:
        rsp.status = _CFG_NOT_FOUND
        return False
    if packet_id <= 0:
        rsp.status = _BAD_REQ
        return False
    now = int(time.time() if now is None else now)
    fingerprint = "supply-box"
    with item_mgr.player_lock(player_id), db.transaction():
        if packet_id > 0:
            operation = _load_operation(player_id, "supply-box", 0, packet_id, fingerprint)
            if operation == "conflict":
                rsp.status = _BAD_REQ
                return False
            if operation is not None:
                rsp.ParseFromString(operation[0])
                pack.ParseFromString(operation[1])
                return True
        next_ts = db.get_kv(player_id, "player", "supply_box_next")
        if next_ts is None:
            created = db.get_players_info(player_id, "create_time")
            next_ts = (int(created[0]) if created and created[0] else now) + interval
        if now < int(next_ts):
            rsp.status = StatusCode.StatusCode_FAIL
            rsp.next_reward_time = int(next_ts)
            return False
        if len(options) == 1:
            rewards = [options[0][1]]
        else:
            rewards = [random.choices([entry[1] for entry in options], weights=[entry[0] for entry in options], k=1)[0]]
        item_mgr.grant_items(player_id, rewards, rsp_items=rsp.items, pack_notice=pack)
        rsp.next_reward_time = now + _supply_interval_seconds()
        db.set_kv(player_id, "player", "supply_box_next", rsp.next_reward_time)
        rsp.status = _OK
        _save_operation(player_id, "supply-box", 0, packet_id, fingerprint, rsp, pack)
    return False


def report_rewards(session, rewards):
    """奖励已提交后推进获取类成就，失败不影响领取结果。"""
    with achieve_track.batch(session):
        for reward in rewards:
            item_id = int(reward.main_item.item_id)
            if reward.main_item.WhichOneof("item") == "base_item":
                count = int(reward.main_item.base_item.num)
            else:
                count = 1
            if item_id > 0 and count > 0:
                achieve_track.report(session, "gain_item", match=item_id, amount=count)
