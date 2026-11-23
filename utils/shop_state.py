"""商店展示、商品池选择与限购周期统一读取当前资源配置。"""

import threading
import time

import utils.db as db
from utils import refresh
from utils.res_loader import res

_purchase_locks = {}


def purchase_lock(player_id):
    """同一玩家的限购检查、扣款和发奖串行，避免免费礼包并发重复领取。"""
    return _purchase_locks.setdefault(player_id, threading.Lock())


def limit_key(grid):
    """展示与购买使用同一周期计数；每日沿用全服游戏日重置时间。"""
    refresh_type = grid.get("new_shop_refresh_type")
    if refresh_type == 2:
        period = f"d{refresh.day_index()}"
    elif refresh_type == 3:
        period = "w" + time.strftime("%G-W%V")
    elif refresh_type == 4:
        period = "m" + time.strftime("%Y%m")
    else:
        period = "p"
    return f"{grid['shop_pool_i_d']}:{period}"


def buy_times(player_id, grid):
    return int(db.get_kv(player_id, "shop_buy", limit_key(grid), 0) or 0)


def grid_rows(shop_id):
    row = next((r for r in res["Shop"]["grid"]["datas"] if r["i_d"] == shop_id), None)
    if row is None:
        return None
    pools = {pool["i_d"]: pool for pool in res["Shop"]["pool"]["datas"]}
    result = []
    for source in row.get("items", ()):
        item = dict(source)
        # grid.index是展示排序，不是商品在pool.items中的index。
        pool_items = pools.get(source["shop_pool_i_d"], {}).get("items", ())
        item["pool_index"] = pool_items[0].get("index", 1) if pool_items else 1
        result.append(item)
    return result
