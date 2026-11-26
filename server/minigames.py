"""Durable multiplayer-room runs and Collapse failure bookkeeping.

MP rewards are opt-in.  The main agent may add Config.MP_ROOM_REWARDS with:
    {(mode_id, sub_mode_id, gameplay_id, star): {
        "items": ((item_id, count), ...),
        "quota_kind": "score" | "extra_bonus" | "extra_mag",  # optional
        "quota_items": ((item_id, count), ...),                # required with quota_kind
    }}
No reward is invented when an entry is absent.
"""

import base64
from contextlib import ExitStack
import json
import threading
import time
import uuid

from config import Config
from proto.net_pb2 import MPPlayRoomSettlementNotice, StatusCode
from server import mp_room_rewards
from utils import item_mgr
import utils.db as db


lock = threading.RLock()
_SYSTEM_PLAYER_ID = 0
_NAMESPACE = "minigame_runs"
_VERSION = 1
_QUOTA_KINDS = ("score", "extra_bonus", "extra_mag")
_COLLAPSE_DEDUP_SECONDS = 2


class RoomStateError(ValueError):
    pass


class RoomRewardConfigError(ValueError):
    pass


def _decode(raw):
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) and value.get("version") == _VERSION else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def load_run(run_id):
    with lock:
        return _decode(db.get_kv(_SYSTEM_PLAYER_ID, _NAMESPACE, str(run_id)))


def save_run(run):
    db.set_kv(
        _SYSTEM_PLAYER_ID, _NAMESPACE, str(run["run_id"]),
        json.dumps(run, sort_keys=True).encode("utf-8"),
    )


def ensure_run(team):
    """Create or recover the durable run for the current in-memory room."""
    room = team.get("room") or {}
    now_ms = int(time.time() * 1000)
    with lock, db.transaction():
        run = load_run(room.get("run_id")) if room.get("run_id") else None
        if run is None:
            current_id = db.get_kv(_SYSTEM_PLAYER_ID, _NAMESPACE, f"current:{team['team_id']}")
            run = load_run(current_id)
            if run and (
                int(run.get("team_id", 0)) != int(team["team_id"])
                or int(run.get("room_start_ms", 0)) != int(room.get("game_start_time", 0))
            ):
                run = None
        if run is None:
            run = {
                "version": _VERSION,
                "run_id": uuid.uuid4().hex,
                "team_id": int(team["team_id"]),
                "room_start_ms": int(room.get("game_start_time", 0) or now_ms),
                "start_ms": 0,
                "end_ms": 0,
                "mode_id": int(team.get("mode_id", 0)),
                "sub_mode_id": int(team.get("sub_mode_id", 0)),
                "gameplay_id": int(team.get("gameplay_id", 0)),
                "play_mode": int(team.get("game_mode", 0)),
                "members": {str(pid): int(member.get("character_id", 0)) for pid, member in team.get("members", {}).items()},
                "status": "ready",
                "star": 0,
                "duration_ms": 0,
                "results": {},
                "exited": [],
            }
            save_run(run)
            db.set_kv(_SYSTEM_PLAYER_ID, _NAMESPACE, f"current:{team['team_id']}", run["run_id"])
        room["run_id"] = run["run_id"]
        return run


def mark_started(team, now_ms):
    with lock, db.transaction():
        run = ensure_run(team)
        if run["status"] == "settled":
            return run
        if not run.get("start_ms"):
            run["start_ms"] = int(now_ms)
            run["status"] = "active"
        save_run(run)
        return run


def exit_member(team, player_id):
    with lock, db.transaction():
        run = ensure_run(team)
        if str(player_id) not in run["exited"]:
            run["exited"].append(str(player_id))
        if run["status"] != "settled" and set(run["exited"]) >= set(run["members"]):
            run["status"] = "abandoned"
            run["end_ms"] = int(time.time() * 1000)
        save_run(run)
        return run


def _reward_plan(run, star):
    table = getattr(Config, "MP_ROOM_REWARDS", {})
    if not isinstance(table, dict):
        raise RoomRewardConfigError("MP_ROOM_REWARDS must be a mapping")
    key = (run["mode_id"], run["sub_mode_id"], run["gameplay_id"], int(star))
    entry = table.get(key)
    if entry is None:
        return (), None, ()
    if not isinstance(entry, dict):
        raise RoomRewardConfigError("MP room reward entry must be a mapping")
    items = tuple(entry.get("items", ()) or ())
    quota_kind = entry.get("quota_kind")
    quota_items = tuple(entry.get("quota_items", ()) or ())
    if quota_kind is not None and quota_kind not in _QUOTA_KINDS:
        raise RoomRewardConfigError("invalid MP room quota kind")
    if quota_kind is not None and not quota_items:
        raise RoomRewardConfigError("quota reward requires quota_items")
    item_mgr.validate_rewards(items)
    item_mgr.validate_rewards(quota_items)
    return items, quota_kind, quota_items


def _grant(player_id, rewards):
    if not rewards:
        return []
    granted = []
    item_mgr.grant_items(player_id, rewards, rsp_items=granted, session=None)
    return [base64.b64encode(item.SerializeToString()).decode("ascii") for item in granted]


def settle(team, star, now_ms=None):
    """Settle once and grant every original member inside one DB transaction."""
    if isinstance(star, bool) or not isinstance(star, int) or not 0 <= star <= 3:
        raise RoomStateError("invalid room star")
    now_ms = int(time.time() * 1000 if now_ms is None else now_ms)
    with lock, db.transaction():
        run = ensure_run(team)
        if run["status"] == "settled":
            return run, False
        if run["status"] != "active" or not run.get("start_ms"):
            raise RoomStateError("room has not started")
        duration = max(0, now_ms - int(run["start_ms"]))
        items, quota_kind, quota_items = _reward_plan(run, star)
        member_ids = sorted(int(pid) for pid in run["members"])
        with ExitStack() as stack:
            for player_id in member_ids:
                stack.enter_context(item_mgr.player_lock(player_id))
            results = {}
            for player_id in member_ids:
                base = _grant(player_id, items)
                extra = []
                if quota_kind and quota_items and mp_room_rewards.consume(player_id, quota_kind, "day", 1):
                    extra = _grant(player_id, quota_items)
                results[str(player_id)] = {"items": base, "extra_items": extra}
            run["status"] = "settled"
            run["star"] = int(star)
            run["duration_ms"] = duration
            run["end_ms"] = now_ms
            run["results"] = results
            save_run(run)
        return run, True


def settlement_notice(run, player_id):
    notice = MPPlayRoomSettlementNotice(
        status=StatusCode.StatusCode_OK,
        gameplay_id=int(run["gameplay_id"]),
        play_mode=int(run["play_mode"]),
        total_consume_time=int(run["duration_ms"]),
    )
    notice.rank.star = int(run["star"])
    result = run.get("results", {}).get(str(player_id), {})
    for encoded in result.get("items", ()):
        notice.rewards.add().ParseFromString(base64.b64decode(encoded))
    for encoded in result.get("extra_items", ()):
        notice.extra_rewards.add().ParseFromString(base64.b64decode(encoded))
    return notice


def collapse_failure(session):
    """Persist a failure and suppress retries in a short protocol-safe window.

    CollapseFailReq has no round id, so exact cross-restart round idempotency is
    impossible.  The latest scene/channel/player timestamp is durable and the
    immutable failure records remain available for audit.
    """
    player_id = int(session.player_id)
    scene_id = int(getattr(session, "scene_id", 0) or 0)
    channel_id = int(getattr(session, "channel_id", 0) or 0)
    identity = f"{player_id}:{scene_id}:{channel_id}"
    now_ms = int(time.time() * 1000)
    with lock, db.transaction():
        latest = _decode(db.get_kv(player_id, "collapse_fail", identity)) or {}
        if now_ms - int(latest.get("time_ms", 0)) < _COLLAPSE_DEDUP_SECONDS * 1000:
            return False, latest.get("failure_id")
        failure_id = uuid.uuid4().hex
        record = {"version": _VERSION, "failure_id": failure_id, "time_ms": now_ms, "player_id": player_id, "scene_id": scene_id, "channel_id": channel_id}
        db.set_kv(player_id, "collapse_fail", failure_id, json.dumps(record, sort_keys=True).encode("utf-8"))
        db.set_kv(player_id, "collapse_fail", identity, json.dumps(record, sort_keys=True).encode("utf-8"))
        return True, failure_id
