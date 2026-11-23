# 餐厅经营小游戏持久化层(RestaurantGame.json)
# 进度已迁移到 utils/db.py 的 player_kv 表, 服务器重启不丢失
from config import Config
import random

from utils.res_loader import res
import utils.db as db


def _sheet(name):
    return res.get("RestaurantGame", {}).get(name, {}).get("datas", ())


def get_global_int(key, default):
    """GlobalConfig.json config: 按 key 取整型值(values[0])"""
    for e in res.get("GlobalConfig", {}).get("config", {}).get("datas", ()):
        if e.get("key") == key:
            vals = e.get("values", ())
            if (
                isinstance(vals, (list, tuple))
                and len(vals) > 0
                and isinstance(vals[0], (int, str))
            ):
                return int(vals[0])
            return default
    return default


def get_desk_bags(activity_id):
    """restaurant_desk_bag(i_d = activity_id): 格子列表
    [{bag_i_d, unlock_dungon_i_d(缺省=默认解锁, 注意表内拼写)}]"""
    for e in _sheet("restaurant_desk_bag"):
        if e.get("i_d") == activity_id:
            return e.get("restaurant_desk_bag_group_info", ())
    return ()


def get_dungeon_cfg(dungeon_id):
    """restaurant_dungeon: 关卡条目(activity_i_d/unlock_dungeon_i_d/is_refresh/
    restaurant_dungeon_group_info=顾客订单[{food_type, food_level, order_quantity}])"""
    for e in _sheet("restaurant_dungeon"):
        if e.get("i_d") == dungeon_id:
            return e
    return None


def get_first_dungeon_id(activity_id):
    """该活动的起始关卡: 无 unlock_dungeon_i_d 且非 is_refresh 的关卡(如 12000 -> 1001)"""
    for e in _sheet("restaurant_dungeon"):
        if (
            e.get("activity_i_d") == activity_id
            and not e.get("unlock_dungeon_i_d")
            and not e.get("is_refresh")
        ):
            return e["i_d"]
    return 0


def get_next_dungeon_id(activity_id, completed_id):
    """完成 completed_id 后解锁的下一关(unlock_dungeon_i_d == completed_id)"""
    for e in _sheet("restaurant_dungeon"):
        if (
            e.get("activity_i_d") == activity_id
            and e.get("unlock_dungeon_i_d") == completed_id
        ):
            return e["i_d"]
    return 0


def get_foods(activity_id):
    """restaurant_game_food(i_d = activity_id): 食物列表"""
    for e in _sheet("restaurant_game_food"):
        if e.get("i_d") == activity_id:
            return e.get("restaurant_game_food_group_info", ())
    return ()


def get_food_cfg(activity_id, food_id):
    for f in get_foods(activity_id):
        if f.get("food_i_d") == food_id:
            return f
    return None


def get_pool_cfg(activity_id, pool_id):
    """restaurant_random_pool: 购买奖池(food 列表 + rate_min/rate_max=购买价格区间)"""
    first = None
    for e in _sheet("restaurant_random_pool"):
        if e.get("activity_i_d") != activity_id:
            continue
        if e.get("i_d") == pool_id:
            return e
        if first is None:
            first = e
    return first if not pool_id else None


def get_quests(activity_id):
    """restaurant_game_quest(i_d = activity_id): {game_quest_i_d: 任务条目}
    条目: game_coin_i_d x game_coin + game_integral_item x game_integral 为奖励,
    param 为目标关卡 id(new_restaurant_game_quest_type 缺省 0=通关任务)"""
    for e in _sheet("restaurant_game_quest"):
        if e.get("i_d") == activity_id:
            return {
                g["game_quest_i_d"]: g
                for g in e.get("restaurant_game_quest_group_info", ())
                if g.get("game_quest_i_d")
            }
    return {}


def get_coin_item_id(activity_id):
    """玩法货币物品 id: 取任务表的 game_coin_i_d(表内为 1601 小游戏金币)"""
    for g in get_quests(activity_id).values():
        if g.get("game_coin_i_d"):
            return g["game_coin_i_d"]
    return Config.RESTAURANT_GAME_COIN_ITEM_ID


def build_customers(activity_id, dungeon_id):
    """按关卡订单生成顾客: index 1 基,
    food = 满足 (food_type, food_level) 的具体食物随机一种,
    remain = order_quantity(供餐该次数后该顾客完成)"""
    customers = {}
    cfg = get_dungeon_cfg(dungeon_id)
    orders = cfg.get("restaurant_dungeon_group_info", ()) if cfg else ()
    foods = get_foods(activity_id)
    for i, order in enumerate(orders, 1):
        candidates = [
            f["food_i_d"]
            for f in foods
            if f.get("food_type") == order.get("food_type")
            and f.get("food_level") == order.get("food_level")
            and f.get("food_i_d")
        ]
        customers[i] = {
            "food": random.choice(candidates) if candidates else 1,
            "remain": max(order.get("order_quantity", 1), 1),
            "status": False,
        }
    return customers


def grid_unlocked(state, bag_cfg):
    """格子解锁: 无 unlock_dungon_i_d 默认解锁, 否则需已通关对应关卡"""
    need = bag_cfg.get("unlock_dungon_i_d", 0)
    return not need or need in state["completed"]


def advance_if_cleared(state, activity_id):
    """全部顾客完成后结算通关: 记录 completed 并进入下一关
    (末关 1030 后进入 is_refresh 循环关 1000, 循环关通关后重开自身)。
    返回是否发生了通关。"""
    customers = state["customers"]
    if not customers or not all(c["status"] for c in customers.values()):
        return False
    dungeon_id = state["dungeon_id"]
    state["completed"].add(dungeon_id)
    next_id = get_next_dungeon_id(activity_id, dungeon_id)
    if not next_id:
        cfg = get_dungeon_cfg(dungeon_id)
        if cfg and cfg.get("is_refresh"):
            next_id = dungeon_id  # 循环关重开
    if next_id:
        state["dungeon_id"] = next_id
        state["customers"] = build_customers(activity_id, next_id)
    return True


def get_state(player_id, activity_id):
    """返回该玩家该活动的餐厅状态"""
    key = (player_id, activity_id)
    state = db.get_restaurant_state(player_id, activity_id)
    if state is not None:
        # set 不能 pickle, 反序列化后恢复
        if not isinstance(state.get("completed"), set):
            state["completed"] = set(state.get("completed", ()))
        if not isinstance(state.get("rewarded_quests"), set):
            state["rewarded_quests"] = set(state.get("rewarded_quests", ()))
        return state
    bags = get_desk_bags(activity_id)
    if bags:
        grids = {b["bag_i_d"]: 0 for b in bags if b.get("bag_i_d")}
    else:
        grids = {i: 0 for i in range(1, Config.RESTAURANT_GRID_COUNT_FALLBACK + 1)}
    dungeon_id = get_first_dungeon_id(activity_id)
    state = {
        # 当前关卡(restaurant_dungeon)
        "dungeon_id": dungeon_id,
        # 已通关关卡 id 集合(用于格子解锁与任务判定)
        "completed": set(),
        # 格子: bag_i_d -> food_i_d(0 表示空)
        "grids": grids,
        # 顾客: index -> {"food", "remain", "status"}
        "customers": build_customers(activity_id, dungeon_id),
        # 已领奖的任务 id
        "rewarded_quests": set(),
        "special_weight": get_global_int("RestaurantGameBaseWeight", 10),
    }
    db.set_restaurant_state(player_id, activity_id, state)
    return state


def save_state(player_id, activity_id, state):
    """持久化餐厅状态"""
    db.set_restaurant_state(player_id, activity_id, state)
