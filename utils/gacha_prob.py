"""官方抽卡概率 + 保底模型（移植自 Lolo game/model/gacha.go，并按官方 UP 池规则修正保底）。

与官方一致的部分
----------------
- 概率单位是「万分比」（100 = 1%）。
- 角色池：SSR 1%（限时池 0.5%）、SR 6%、SSR 海报 0.8%、SR 海报 92.2%；
  SR 每 10 抽必出，SSR 每 N 抽必出（N 见 `pity_cap`）。
- 服装池：服装 2% / 家具 50% / 武器金 4% / 武器紫 35% / 染色剂 9%，
  服装每 10 抽必出，愿望保底 70 且概率随抽数渐增。

按玩家反馈修正的部分（与原版 Lolo 不同）
------------------------------------
1. **保底按「卡池」独立计数**，不是按类型共享 —— 限时 UP 池 A 的保底不会被普池消耗。
2. 歪到「非本卡池 UP」的 SSR **不清空保底计数**，只有抽到本卡池 UP 才清零。
3. 保底触发时**必定给本卡池 UP**（优先 `character_i_d1`），不会再给随机 SSR。

计数持久化在 `player_kv`：
- `gacha_banner` / `"<gacha_id>:ssr"` —— 本卡池 SSR 保底计数
- `gacha_type`   / `"guarantee_sr"`   —— 类型级 SR 保底计数
- `gacha_type`   / `"guarantee_fashion"` / `"guarantee_desire"` —— 服装池计数

对外接口
------
    draw_batch(player_id, gacha_id, type_id, info, pools, big_items, count, optional_item_id=0)
        -> [(item_id, kind), ...]
    remaining(player_id, gacha_id, type_id, info) -> int   # 本卡池 SSR 保底还剩多少抽
"""

import random

import utils.db as db

KIND_CHARACTER_SSR = "character_ssr"        # 歪到的 SSR（非本池 UP）
KIND_CHARACTER_SSR_UP = "character_ssr_up"  # 本池 UP 的 SSR
KIND_CHARACTER_SR = "character_sr"
KIND_POSTER_SSR = "poster_ssr"
KIND_POSTER_SR = "poster_sr"
KIND_FASHION = "fashion"
KIND_DESIRE = "desire"
KIND_FURNITURE = "furniture"
KIND_WEAPON_SSR = "weapon_ssr"
KIND_WEAPON_SR = "weapon_sr"
KIND_DYE_STUFF = "dye_stuff"

POOL_SSR = 400
POOL_SR = 300
POOL_SSR_POSTER = 200
POOL_SR_POSTER = 100
POOL_DYE_STUFF = 40000
POOL_FURNITURE = 40001
POOL_WEAPON_SR = 40002
POOL_WEAPON_SSR = 40003
POOL_FASHION = 40004

NS_BANNER = "gacha_banner"
NS_TYPE = "gacha_type"

_TABLE = None

_FALLBACK = {7: 6, 10: 6, 11: 6, 12: 6, 13: 6, 14: 6, 15: 6, 16: 6, 17: 6,
             18: 6, 19: 6, 20: 6, 21: 6, 22: 6, 23: 6}


def table():
    global _TABLE
    if _TABLE is None:
        from utils.res_loader import res

        raw = res.get("GachaProbability") or {}
        _TABLE = {int(k): v for k, v in raw.items()}
    return _TABLE


def rules(type_id):
    t = table()
    for tid in (int(type_id), _FALLBACK.get(int(type_id)), 2, 1):
        if tid is not None and tid in t:
            return t[tid]
    return {}


# ---------------------------------------------------------------- 计数读写

def _kv_get(ns, player_id, key):
    try:
        return int(db.get_kv(player_id, ns, key, 0) or 0)
    except Exception:
        return 0


def _kv_set(ns, player_id, key, value):
    try:
        db.set_kv(player_id, ns, key, int(value))
    except Exception:
        pass


def _banner_key(gacha_id):
    """SSR 保底计数键：所有卡池共享同一个计数（按类别区分服装池）。"""
    if int(gacha_id or 0) and _shared_mode():
        return "all:ssr"
    return "%s:ssr" % int(gacha_id)


def _shared_mode():
    """True = 所有卡池继承同一个保底计数（官方实际行为，客户端也只显示一条）。"""
    try:
        from config import Config

        return bool(getattr(Config, "GACHA_PITY_SHARED", True))
    except Exception:
        return True


def pity_cap(info, type_id):
    """本卡池的 SSR 保底抽数：优先 config.GACHA_PITY_SSR，其次 max_times，再次概率表，最后 70。"""
    try:
        from config import Config

        override = int(getattr(Config, "GACHA_PITY_SSR", 0) or 0)
    except Exception:
        override = 0
    if override > 0:
        return override
    try:
        mt = int((info or {}).get("max_times") or 0)
    except Exception:
        mt = 0
    if mt > 0:
        return mt
    return int(rules(type_id).get("guaranteeSSR") or 70)


def up_primary(info, big_items):
    """本卡池的 UP 主物品（保底必给的那一个）。

    取法优先 character_i_d1..3（官方角色 UP 池）；若都为 0（例如 3023 这种
    「海报/映像」UP 池，官方把 UP 放在 big_guarantee_pool 里且只有一条），
    则在大奖池只有 1 个物品时认定它就是 UP。多物品且无 character_i_d 时
    视为「无 UP 的普池」，返回 0（保底退化为随机 SSR）。
    """
    info = info or {}
    for key in ("character_i_d1", "character_i_d2", "character_i_d3"):
        try:
            cid = int(info.get(key) or 0)
        except Exception:
            cid = 0
        if cid:
            return cid
    items = [i for i in (big_items or []) if i]
    if len(items) == 1:
        return int(items[0])
    return 0


def remaining(player_id, gacha_id, type_id, info):
    """SSR 保底还剩多少抽（给 UI 显示）。共享模式下所有卡池返回同一个值。"""
    cap = pity_cap(info, type_id)
    if _shared_mode():
        used = _kv_get(NS_BANNER, player_id, "all:ssr")
    else:
        used = _kv_get(NS_BANNER, player_id, _banner_key(gacha_id))
    return max(0, cap - used)


# ---------------------------------------------------------------- 抽取

def _pick(items):
    return random.choice(items)


def _dbg(msg):
    """抽卡诊断日志：写入 logs/gacha_debug.log（失败静默）。"""
    try:
        import os
        import time

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "logs", "gacha_debug.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def _draw_character(player_id, gacha_id, type_id, info, pools, big_items, optional_item_id=0):
    r = rules(type_id)
    gsr = int(r.get("guaranteeSR") or 10)
    p_ssr = int(r.get("probabilitySSR") or 100)
    p_sr = int(r.get("probabilitySR") or 600)
    p_poster_ssr = int(r.get("probabilityPosterSSR") or 80)

    key = _banner_key(gacha_id)
    cnt = _kv_get(NS_BANNER, player_id, key) + 1
    cap = pity_cap(info, type_id)
    up_id = up_primary(info, big_items)

    # SR 保底：类型级计数，与 SSR 保底互不影响
    cnt_sr = _kv_get(NS_TYPE, player_id, "guarantee_sr") + 1
    sr_guarantee = cnt_sr == gsr - 1

    # 1) 本卡池 SSR 保底触发 —— 必定给 UP
    if cnt >= cap:
        _kv_set(NS_BANNER, player_id, key, 0)
        _kv_set(NS_TYPE, player_id, "guarantee_sr", cnt_sr)
        item = up_id or (_pick(big_items) if big_items else 0)
        _dbg("PITY gacha=%s type=%s cnt=%s cap=%s up=%s -> %s"
             % (gacha_id, type_id, cnt, cap, up_id, item))
        return item, KIND_CHARACTER_SSR_UP

    # 2) SR 保底
    if sr_guarantee:
        pool = pools.get(POOL_SR) or pools.get(POOL_SSR)
        _kv_set(NS_BANNER, player_id, key, cnt)
        _kv_set(NS_TYPE, player_id, "guarantee_sr", 0)
        return (_pick(pool) if pool else 0), KIND_CHARACTER_SR

    _kv_set(NS_TYPE, player_id, "guarantee_sr", cnt_sr)

    # 3) 正常概率
    n = random.randint(1, 10000)
    n -= p_ssr
    if n <= 0:
        # 50% 走本池 UP 池，否则走常驻 SSR 池
        if big_items and random.randint(1, 10000) > 5000:
            item = _pick(big_items)
            is_up = (item == up_id) or (not up_id)
        else:
            pool = pools.get(POOL_SSR)
            item = _pick(pool) if pool else 0
            is_up = bool(up_id) and item == up_id
        # 只有抽到本池 UP 才清空保底；歪到别的 SSR 保留计数
        _kv_set(NS_BANNER, player_id, key, 0 if is_up else cnt)
        return item, (KIND_CHARACTER_SSR_UP if is_up else KIND_CHARACTER_SSR)

    n -= p_sr
    if n <= 0:
        pool = pools.get(POOL_SR) or pools.get(POOL_SSR)
        _kv_set(NS_BANNER, player_id, key, cnt)
        _kv_set(NS_TYPE, player_id, "guarantee_sr", 0)
        return (_pick(pool) if pool else 0), KIND_CHARACTER_SR

    n -= p_poster_ssr
    _kv_set(NS_BANNER, player_id, key, cnt)
    if n <= 0:
        pool = pools.get(POOL_SSR_POSTER)
        return (_pick(pool) if pool else 0), KIND_POSTER_SSR
    pool = pools.get(POOL_SR_POSTER)
    return (_pick(pool) if pool else 0), KIND_POSTER_SR


def _draw_fashion(player_id, gacha_id, type_id, info, pools, optional_item_id=0):
    r = rules(type_id)
    gf = int(r.get("guaranteeFashion") or 10)
    gd = int(r.get("guaranteeDesire") or 70)
    p_fashion = int(r.get("probabilityFashion") or 200)
    p_furniture = int(r.get("probabilityFurniture") or 5000)
    p_wpn_ssr = int(r.get("probabilityWeaponSSR") or 400)
    p_wpn_sr = int(r.get("probabilityWeaponSR") or 3500)

    cnt_desire = _kv_get(NS_TYPE, player_id, "guarantee_desire") + 1
    cnt_fashion = _kv_get(NS_TYPE, player_id, "guarantee_fashion") + 1
    _kv_set(NS_TYPE, player_id, "guarantee_desire", cnt_desire)
    _kv_set(NS_TYPE, player_id, "guarantee_fashion", cnt_fashion)

    if cnt_fashion == gf - 1:
        pool = pools.get(POOL_FASHION)
        _kv_set(NS_TYPE, player_id, "guarantee_fashion", 0)
        return (_pick(pool) if pool else 0), KIND_FASHION

    if optional_item_id and cnt_desire >= gd:
        _kv_set(NS_TYPE, player_id, "guarantee_desire", 0)
        return int(optional_item_id), KIND_DESIRE

    n = random.randint(1, 10000)
    n -= cnt_desire * 50
    if n <= 0 and optional_item_id:
        _kv_set(NS_TYPE, player_id, "guarantee_desire", 0)
        return int(optional_item_id), KIND_DESIRE
    n -= p_fashion
    if n <= 0:
        pool = pools.get(POOL_FASHION)
        _kv_set(NS_TYPE, player_id, "guarantee_fashion", 0)
        return (_pick(pool) if pool else 0), KIND_FASHION
    n -= p_furniture
    if n <= 0:
        pool = pools.get(POOL_FURNITURE)
        return (_pick(pool) if pool else 0), KIND_FURNITURE
    n -= p_wpn_ssr
    if n <= 0:
        pool = pools.get(POOL_WEAPON_SSR)
        return (_pick(pool) if pool else 0), KIND_WEAPON_SSR
    n -= p_wpn_sr
    if n <= 0:
        pool = pools.get(POOL_WEAPON_SR)
        return (_pick(pool) if pool else 0), KIND_WEAPON_SR
    pool = pools.get(POOL_DYE_STUFF)
    return (_pick(pool) if pool else 0), KIND_DYE_STUFF


def draw_batch(player_id, gacha_id, type_id, info, pools, big_items, count, optional_item_id=0):
    """抽 count 次，返回 [(item_id, kind), ...]；item_id 为 0 表示池缺失，调用方需兜底。"""
    type_id = int(type_id or 2)
    out = []
    for _ in range(int(count)):
        if type_id == 5:
            item, kind = _draw_fashion(player_id, gacha_id, type_id, info, pools, optional_item_id)
        else:
            item, kind = _draw_character(player_id, gacha_id, type_id, info, pools, big_items, optional_item_id)
        out.append((item or 0, kind))
    return out
