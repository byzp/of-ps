# -*- coding: utf-8 -*-
"""宝箱索引解析与状态回放。"""

from config import Config
import time
import threading

from proto.net_pb2 import TreasureBoxData
from proto.net_pb2 import TreasureBoxLocType_DUNGEON
from proto.net_pb2 import TREASURE_BOX_TYPE_DYNAMIC

import utils.db as db
from utils.res_loader import res

_box_locks = {}


def player_box_lock(player_id):
    """同一玩家开箱、领取、重置互斥，避免重复发奖和重复扣体力。"""
    return _box_locks.setdefault(player_id, threading.Lock())


def reset_dungeon_boxes(player_id, dungeon_id):
    """新一轮材料本清除上一轮箱状态和扣费标记，不影响世界箱。"""
    prefix = f"dungeon:{dungeon_id}:"
    with player_box_lock(player_id):
        for key, _blob in db.get_treasure_box_records(player_id):
            if isinstance(key, str) and key.startswith(prefix):
                db.delete_treasure_box(player_id, key)
        for namespace in ("dungeon_box_paid", "dungeon_box_multiple"):
            for key in db.get_kv_keys(player_id, namespace):
                if key.startswith(prefix):
                    db.del_kv(player_id, namespace, key)


def normalize_refresh_time(timestamp):
    """Return refresh timestamps in Unix seconds (older records may be ms)."""
    if timestamp >= 100_000_000_000:
        return timestamp // 1000
    return timestamp


def refresh_interval(box_id, is_dungeon=False):
    """Return configured interval, using the observed scene default if absent."""
    for row in res["TreasureBox"]["collection_treasure_box"]["datas"]:
        if row.get("i_d") != box_id:
            continue
        refresh_time = row.get("refresh_time")
        if not isinstance(refresh_time, (list, tuple)) or not refresh_time:
            return 0
        interval = int(refresh_time[0])
        return interval if interval > 0 else 0
    return 0 if is_dungeon else Config.DEFAULT_SCENE_REFRESH_INTERVAL


def expire_due_records(player_id, scene_id=0, dungeon_id=0, now=None):
    """删除目标场景中到期的静态刷新箱记录, 使其回到未开启状态。"""
    now = int(now if now is not None else time.time())
    prefix = f"dungeon:{int(dungeon_id)}:" if dungeon_id else f"scene:{int(scene_id)}:"

    did_expire = False
    for store_key, blob in db.get_treasure_box_records(player_id):
        if not isinstance(store_key, str) or not store_key.startswith(prefix):
            continue
        saved = TreasureBoxData()
        saved.ParseFromString(blob)
        normalized_time = normalize_refresh_time(saved.next_refresh_time)
        if normalized_time != saved.next_refresh_time:
            saved.next_refresh_time = normalized_time
            db.set_treasure_box(player_id, store_key, saved.SerializeToString())
        interval = refresh_interval(saved.box_id, is_dungeon=bool(dungeon_id))
        is_expired = interval > 0 and (
            (saved.next_refresh_time > 0 and saved.next_refresh_time <= now)
            or (saved.next_refresh_time == 0 and not saved.rewards)
        )
        if is_expired:
            db.delete_treasure_box(player_id, store_key)
            did_expire = True
    return did_expire


def static_store_key(session, index, loc_type=0):
    """返回静态宝箱的场景/副本隔离键。"""
    if loc_type == TreasureBoxLocType_DUNGEON:
        dungeon = getattr(session, "dungeon", None)
        dungeon_id = dungeon[0] if dungeon else 0
        return f"dungeon:{dungeon_id}:{int(index)}"
    return f"scene:{getattr(session, 'scene_id', 0)}:{int(index)}"


def load_record(player_id, store_key, legacy_index=None):
    """读取宝箱状态，并兼容旧版本按裸点位序号保存的记录。"""
    blob = db.get_treasure_box(player_id, store_key)
    used_legacy = False
    if (
        not blob
        and legacy_index is not None
        and isinstance(store_key, str)
        and not store_key.startswith("dungeon:")
    ):
        blob = db.get_treasure_box(player_id, legacy_index)
        used_legacy = bool(blob)
    return blob, used_legacy


def resolve(session, box_type, index, loc_type=0):
    """解析失败返回 None(调用方回 TREASURE_BOX_NOT_EXIST)。
    loc_type=TreasureBoxLocType_DUNGEON 且 box_type=STATIC 时, 索引指向
    当前副本 Dungeons[ID].CollectionTreasureInfos(官方 EnterRsp 同源,
    pack0/1772958201 实锤副本箱可开)。"""

    if box_type == TREASURE_BOX_TYPE_DYNAMIC:
        v = db.get_kv(session.player_id, "dyn_box", index, "")
        if not v:
            return None
        return -int(index), int(v)
    if loc_type == TreasureBoxLocType_DUNGEON:
        cur = getattr(session, "dungeon", None)
        dungeon_id = cur[0] if cur else 0
        if not dungeon_id:
            return None
        for dg in res.get("ScenesConfigAsset", {}).get("Dungeons", ()) or ():
            if not isinstance(dg, dict) or dg.get("ID") != dungeon_id:
                continue
            for pos, c in enumerate(dg.get("CollectionTreasureInfos") or ()):
                if not isinstance(c, dict):
                    continue
                if c.get("Index", pos) == index and c.get("ID"):
                    return static_store_key(session, index, loc_type), c["ID"]
            return None
        return None
    scene_id = getattr(session, "scene_id", 0)
    for sc in res.get("ScenesConfigAsset", {}).get("Scenes", ()) or ():
        if not isinstance(sc, dict) or sc.get("ID") != scene_id:
            continue
        for pos, c in enumerate(sc.get("CollectionTreasureInfos") or ()):
            if not isinstance(c, dict):
                continue
            if c.get("Index", pos) == index and c.get("ID"):
                return static_store_key(session, index), c["ID"]
        return None
    return None
