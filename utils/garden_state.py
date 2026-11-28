"""花园与探索玩法的持久化层，状态存 player_kv。"""

from config import Config
from utils import item_mgr as items_util

from proto.net_pb2 import ItemDetail


import random
import time

import utils.db as db
from utils.res_loader import res


def now_ms():
    return int(time.time() * 1000)


# ---------------- Explore.json 配置访问(容错, 表缺失返回空/None) ----------------


def explore_area_cfg(explore_id):
    """Explore.json explore_area 行, 不存在返回 None"""
    for row in res["Explore"]["explore_area"]["datas"]:
        if row.get("i_d") == explore_id:
            return row
    return None


def explore_area_ids():
    """全部探索点 id(Explore.json explore_area.i_d)"""
    return [r["i_d"] for r in res["Explore"]["explore_area"]["datas"] if "i_d" in r]


def explore_collect_items(explore_id):
    """探索点采集物列表(Explore.json explore_area.explore_area_item.rewar_item_i_d)"""
    cfg = explore_area_cfg(explore_id)
    if not cfg:
        return []
    return [
        it["rewar_item_i_d"]
        for it in cfg.get("explore_area_item", ())
        if it.get("rewar_item_i_d")
    ]


def interval_cfg(interval_id):
    """Explore.json explore_interval 行, 不存在返回 None"""
    for row in res["Explore"]["explore_interval"]["datas"]:
        if row.get("i_d") == interval_id:
            return row
    return None


def random_interval_cfg():
    """随机取一条 explore_interval 配置(开启新间隙用), 表缺失返回 None"""
    rows = res["Explore"]["explore_interval"]["datas"]
    if rows:
        return random.choice(rows)
    return None


# ---------------- 探索 ----------------


def get_explore(player_id, explore_id):
    """获取(必要时创建)玩家某探索点的进度 dict"""
    return db.get_explore(player_id, explore_id)


def set_explore(player_id, explore_id, state):
    """持久化探索进度"""
    db.set_explore(player_id, explore_id, state)


def fill_explore_info(info, explore_id, e):
    """把进度写入 PlayerExploreInfo, 采集物取 Explore.json explore_area_item"""
    info.explore_id = explore_id
    info.times = e["times"]
    info.start_time = e["start_time"]
    info.is_quick_finish = e["is_quick_finish"]
    del info.collect_item_id[:]
    for item_id in explore_collect_items(explore_id):
        info.collect_item_id.append(item_id)
    info.collect_reward = e["collect_reward"]


# ---------------- 好友间隙 ----------------


def get_interval(player_id, create=False):
    """获取玩家自己的间隙; create=True 时不存在则新建。
    新建时随机选一条 explore_interval 配置, 持续时长取表字段 time(秒)。"""
    info = db.get_interval(player_id)
    if info is None and create:
        t = now_ms()
        cfg = random_interval_cfg()
        if cfg:
            interval_id = cfg.get("i_d", Config.DEFAULT_INTERVAL_ID)
            duration_ms = cfg.get("time", 0) * 1000 or Config.INTERVAL_DURATION_MS
        else:
            interval_id = Config.DEFAULT_INTERVAL_ID
            duration_ms = Config.INTERVAL_DURATION_MS
        info = {
            "interval_id": interval_id,
            "finish_time": t + duration_ms,
            "create_time": t,
            "member": [],
        }
        db.set_interval(player_id, info)
    return info


def reset_interval(player_id):
    """删除玩家当前的间隙(用于重新开启)"""
    db.del_interval(player_id)


def set_interval(player_id, state):
    """持久化间隙状态"""
    db.set_interval(player_id, state)


# ---------------- 家具方案 ----------------


def save_scheme(player_id, scheme_id, furnitures):
    schemes = db.get_schemes(player_id)
    sch = schemes.setdefault(scheme_id, {"name": "", "furnitures": []})
    sch["furnitures"] = list(furnitures)
    db.set_schemes(player_id, schemes)


def get_scheme(player_id, scheme_id):
    schemes = db.get_schemes(player_id)
    return schemes.get(scheme_id)


def set_scheme_name(player_id, scheme_id, name):
    schemes = db.get_schemes(player_id)
    sch = schemes.setdefault(scheme_id, {"name": "", "furnitures": []})
    sch["name"] = name
    db.set_schemes(player_id, schemes)


def get_scheme_names(player_id):
    """返回 {scheme_id: name}"""
    schemes = db.get_schemes(player_id)
    return {k: v["name"] for k, v in schemes.items()}


# ---------------- 花园开关/密码 ----------------


def set_garden_password(player_id, password, expire_time):
    db.set_garden_password(player_id, password, expire_time)


def get_garden_password(player_id):
    return db.get_garden_password(player_id)


# ---------------- 点赞 ----------------


def consume_like(player_id):
    """消耗一次今日点赞次数, 返回剩余次数; 用尽返回 None"""
    return db.consume_like(player_id, Config.DAILY_LIKE_LIMIT)


def get_like_left(player_id):
    return db.get_like_left(player_id, Config.DAILY_LIKE_LIMIT)


def add_like_record(target_player_id, liker_player_id):
    db.add_like_record(target_player_id, liker_player_id)


def get_like_records(player_id):
    """返回 [(点赞者 player_id, 次数)]"""
    return db.get_like_records(player_id)


# ---------------- 发奖/扣道具(委托 utils/items.py) ----------------


def adjust_furniture_count(player_id, delta):
    like_num, access_num, current, limit, is_open = db.get_garden_info(player_id)
    updated = max(0, current + int(delta))
    db.set_garden_info(player_id, like_num, access_num, updated, limit, is_open)
    return updated, limit


def grant_stack_item(player_id, item_id, num):
    """给玩家增加 num 个可堆叠物品并持久化。
    返回 (gain, total): gain 为本次获得数量的 ItemDetail(放 Rsp 展示),
    total 为增加后的完整 ItemDetail(放 PackNotice 同步背包)。
    """

    totals = items_util.grant_items(player_id, [(item_id, num)])
    if not totals:
        return None, None
    total = totals[0]

    gain = ItemDetail()
    gain.CopyFrom(total)
    gain.main_item.base_item.num = num
    return gain, total


def consume_stack_item(player_id, item_id, num):
    """扣除玩家 num 个可堆叠物品并持久化。
    数量足够返回扣除后的完整 ItemDetail(放 PackNotice 同步背包), 不足返回 None。
    """

    pack = None
    if items_util.consume_items(player_id, [(item_id, num)]):
        # consume_items 成功后重新读取总量(已在锁内写回)

        raw = db.get_item_detail(player_id, item_id)
        if raw:
            total = ItemDetail()
            total.ParseFromString(raw)
            return total
    return None
