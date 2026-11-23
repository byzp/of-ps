"""dungeon 组 handler 共用: 副本掉落生成与可堆叠物品收支。

make_dungeon_rewards 保留装备实例及副本等级，其余收支接口只适用于堆叠物品。
物品收支统一走 utils/item_mgr.py 的 per-player lock。
"""

import random

from config import Config
from proto.net_pb2 import TreasureBoxLocType_DUNGEON, DungeonData
import utils.db as db
from utils import item_mgr
from utils.pb_create import make_item
from utils.res_loader import res
from utils.reward_resolver import resolve_reward, resolve_world_reward
from utils.equipment_pool import random_equipment_ids


def dungeon_config(dungeon_id):
    """返回 Dungeon.dungeon 配置；不存在时返回 None。"""
    return next(
        (row for row in res["Dungeon"]["dungeon"]["datas"] if row["i_d"] == dungeon_id),
        None,
    )


def material_dungeon(session, loc_type):
    """仅静态副本场景中的特训箱使用材料本奖励，不受外界scene_id影响。"""
    from_scene = session.dungeon[0] if loc_type == TreasureBoxLocType_DUNGEON else 0
    cfg = dungeon_config(from_scene)
    if cfg and cfg.get("new_mission_type") == Config.MATERIAL_DUNGEON_TYPE:
        return cfg
    return None


def prerequisite_finished(player_id, cfg):
    """dungeon_i_d为前置副本，至少通关一次才解锁当前难度。"""
    previous_id = cfg.get("dungeon_i_d")
    if not previous_id:
        return True
    blob = db.get_dungeon(player_id, previous_id)
    return bool(blob and DungeonData.FromString(blob).finish_times > 0)


def reward_multiplier(player_id, dungeon_id):
    """玩家为指定副本选择的领取倍率，未设置时为单份。"""
    return int(db.get_kv(player_id, "preferences", f"dungeon_multi:{dungeon_id}", 1))


def sync_multiplier(player_id, req, rsp):
    """params=[副本ID, 倍率]；查询携带副本ID，回包补充该副本倍率。"""
    if not req.params:
        return False
    dungeon_id = req.params[0].int_value
    if not dungeon_config(dungeon_id):
        return False
    if len(req.params) >= 2:
        multiple = req.params[1].int_value
        if multiple not in Config.DUNGEON_REWARD_MULTIPLIERS:
            return False
        db.set_kv(player_id, "preferences", f"dungeon_multi:{dungeon_id}", multiple)
    else:
        rsp.params.add().int_value = reward_multiplier(player_id, dungeon_id)
    return True


def make_dungeon_rewards(player_id, cfg, multiple=1):
    """按副本难度生成 ItemDetail 列表，宝箱和扫荡共用。

    客户端仅包含奖励展示池，没有特训实际掉落池。保留配置种类/品质，
    缺少的数量使用Config中明确标注的本地规则；不以玩家等级扩充掉落池。
    """
    chain = [cfg]
    seen = {cfg["i_d"]}
    previous = dungeon_config(cfg.get("dungeon_i_d"))
    while previous and previous["i_d"] not in seen:
        seen.add(previous["i_d"])
        chain.append(previous)
        previous = dungeon_config(previous.get("dungeon_i_d"))
    counts = Config.DUNGEON_DROP_COUNTS_BY_TIER
    count = counts[min(len(chain), len(counts)) - 1]
    shows = {r["i_d"]: r for r in res["Manual"]["manual_show_reward"]["datas"]}
    # 高难度有999999999占位，沿前置难度链取最近有效的展示池。
    show = next(
        (
            shows[c["show_reward_i_d"]]
            for c in chain
            if c.get("show_reward_i_d") in shows
        ),
        None,
    )
    if not show:
        return []
    entries = show.get("manual_reward_items", ())
    tags = {r["i_d"]: r.get("new_bag_item_tag") for r in res["Item"]["item"]["datas"]}
    equipment = [
        r["item_i_d"] for r in entries if r.get("item_i_d") in random_equipment_ids()
    ]
    result = []
    for row in entries:
        iid = row.get("item_i_d")
        if not iid or tags.get(iid) in (2, 3) or row.get("need_items"):
            continue
        # 经验/金币是明确展示数量，素材随难度增长。
        num = row.get("show_num", 1)
        if iid not in (1, 101):
            num *= count
        num *= multiple
        if num > 0:
            result.append(make_item(iid, num, player_id))
    for _ in range(count * multiple if equipment else 0):
        result.append(
            make_item(
                random.choice(equipment),
                1,
                player_id,
                equipment_level=max(1, cfg.get("monster_lv", 1)),
            )
        )
    return result


def resolve_drop(reward_id, world_level=0, player_level=0):
    """解析掉落 reward_id -> [(item_id, count)]。

    实际数据(Reward.json)中 world_level_pool.pool_i_d 指向的是 reward_pool
    条目(如 Dungeon.dungeon.reward_i_d / Monster.reward_pool_i_d 均为
    world_level_pool 单组自引用, 无世界等级分池), 因此先按世界等级池解析,
    解析为空时回落到 reward_pool 直接解析。
    """
    items_list = resolve_world_reward(reward_id, world_level, player_level)
    if items_list:
        return items_list
    return resolve_reward(reward_id, player_level)


def grant_stack_item(player_id, item_id, num, rewards=None, pack_notice=None):
    """发放 item_id x num 的可堆叠物品。

    rewards: Rsp 中的 repeated ItemDetail 字段(记录本次获得的数量), 可为 None
    pack_notice: PackNotice 消息(记录叠加后的背包总数), 可为 None
    返回叠加后的 ItemDetail。
    """
    totals = item_mgr.grant_items(
        player_id, [(item_id, num)], rsp_items=rewards, pack_notice=pack_notice
    )
    return totals[0] if totals else None


def grant_items(player_id, items_list, rewards=None, pack_notice=None):
    """按 [(item_id, num), ...] 批量发放可堆叠物品"""
    item_mgr.grant_items(
        player_id,
        [(iid, n) for iid, n in items_list if iid and n > 0],
        rsp_items=rewards,
        pack_notice=pack_notice,
    )


def get_stack_num(player_id, item_id):
    """查询背包内可堆叠物品数量"""
    return item_mgr.get_num(player_id, item_id)


def consume_stack_item(player_id, item_id, num, pack_notice=None):
    """扣除 item_id x num 的可堆叠物品, 数量不足返回 False(不扣)。

    pack_notice: PackNotice(items 填扣除后的背包剩余量), 可为 None
    """
    return item_mgr.consume_items(player_id, [(item_id, num)], pack_notice=pack_notice)
