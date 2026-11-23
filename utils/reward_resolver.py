from config import Config
import random

from utils.res_loader import res

_idx = None


def _index():
    """懒构建 Reward 表索引: reward_pool / reward_item_pool / world_level_pool

    无锁惰性初始化(锁纪律: 禁止跨玩家全局锁): 构建只读且幂等,
    无 GIL 下并发首次调用最多重复构建一次, 结果一致, 竞态无害。
    """
    global _idx
    idx = _idx
    if idx is not None:
        return idx
    r = res.get("Reward")
    _pools = ("reward_pool", "reward_item_pool", "world_level_pool")
    if not isinstance(r, dict) or not all(
        isinstance(r.get(p), dict) and isinstance(r[p].get("datas"), (list, tuple))
        for p in _pools
    ):
        idx = {"pool": {}, "item": {}, "world": {}}
    else:
        idx = {
            "pool": {e["i_d"]: e for e in r["reward_pool"]["datas"]},
            "item": {e["i_d"]: e for e in r["reward_item_pool"]["datas"]},
            "world": {e["i_d"]: e for e in r["world_level_pool"]["datas"]},
        }
    _idx = idx
    return idx


def _roll_item_pool(pool_id, player_level=0):
    """reward_item_pool 单池 -> [(item_id, count)], 按玩家等级过滤区间, 数量取 min~max 随机"""
    out = []
    entry = _index()["item"].get(pool_id)
    if not entry:
        return out
    for g in entry.get("reward_item_pool_group", ()):
        item_id = g.get("item_i_d")
        if not item_id:
            continue
        lo = g.get("min_level_limit", 0)
        hi = g.get("max_level_limit", 0)
        if player_level and lo and player_level < lo:
            continue
        if player_level and hi and player_level > hi:
            continue
        cmin = g.get("item_min_count", 1)
        cmax = g.get("item_max_count", cmin)
        out.append((item_id, random.randint(min(cmin, cmax), max(cmin, cmax))))
    return out


def resolve_reward(reward_id, player_level=0):
    """解析 reward_pool 入口的奖励 id -> [(item_id, count)]; 无效/哨兵返回 []"""
    if not reward_id or reward_id == Config.NONE_REWARD:
        return []
    out = []
    entry = _index()["pool"].get(reward_id)
    if entry:
        for g in entry.get("reward_pool_group", ()):
            out.extend(_roll_item_pool(g.get("reward_pool_group_i_d"), player_level))
        if out:
            return out
    # 回落: 部分 reward_id 直接是 reward_item_pool 条目
    # (如 Riddle.reward_pool_i_d=2001 -> 物品192x10)
    out.extend(_roll_item_pool(reward_id, player_level))
    return out


def resolve_drop(reward_id, world_level=0, player_level=0):
    """解析掉落 reward_id -> [(item_id, count)]。

    实际数据(Reward.json)中 world_level_pool.pool_i_d 指向的是 reward_pool
    条目(如 Dungeon.dungeon.reward_i_d / Monster.reward_pool_i_d 均为
    world_level_pool 单组自引用, 无世界等级分池), 因此先按世界等级池解析,
    解析为空时回落到 reward_pool 直接解析。(原 utils/dungeon_reward.resolve_drop)
    """
    items = resolve_world_reward(reward_id, world_level, player_level)
    if items:
        return items
    return resolve_reward(reward_id, player_level)


def resolve_world_reward(reward_id, world_level=0, player_level=0):
    """解析 world_level_pool 入口的奖励 id, 按世界等级选池 -> [(item_id, count)]
    组内条目 world_level 缺省为 0(通用); 优先取等于当前世界等级的条目, 否则取通用条目。"""
    if not reward_id or reward_id == Config.NONE_REWARD:
        return []
    entry = _index()["world"].get(reward_id)
    if not entry:
        return []
    groups = entry.get("world_level_pool_group", ())
    matched = [g for g in groups if g.get("world_level", 0) == world_level]
    if not matched:
        matched = [g for g in groups if not g.get("world_level", 0)]
    out = []
    for g in matched:
        out.extend(_roll_item_pool(g.get("pool_i_d"), player_level))
    return out
