"""手册(Manual)资源表解析 —— ManualFlagReward / ManualList 共用。

两张旗帜表都用 un_lock_reward_i_d -> Reward.reward_pool 领取解锁奖励
(全部为 201 -> 金币x1000)。reward_i_d 是副本掉落展示，不参与解锁领奖。
"""

from utils.res_loader import res
from utils.reward_resolver import resolve_reward


def iter_flags():
    """遍历 manual + manual_dungeon 的所有旗帜, yield (flag_id, 来源表名, 条目)"""
    _man = (
        res["Manual"]["manual"]["datas"]
        if (
            isinstance(res.get("Manual"), dict)
            and isinstance(res["Manual"].get("manual"), dict)
        )
        else ()
    )
    for m in _man if isinstance(_man, (list, tuple)) else ():
        for f in m.get("manual_items", ()):
            if f.get("flag_i_d"):
                yield f["flag_i_d"], "manual", f
    _dun = (
        res["Manual"]["manual_dungeon"]["datas"]
        if (
            isinstance(res.get("Manual"), dict)
            and isinstance(res["Manual"].get("manual_dungeon"), dict)
        )
        else ()
    )
    for m in _dun if isinstance(_dun, (list, tuple)) else ():
        for f in m.get("manual_dungeon_items", ()):
            if f.get("flag_i_d"):
                yield f["flag_i_d"], "manual_dungeon", f


def flag_reward_list(sheet, cfg, player_level):
    """按旗帜来源解析真实奖励 -> [(item_id, num)]"""
    return resolve_reward(cfg.get("un_lock_reward_i_d"), player_level)
