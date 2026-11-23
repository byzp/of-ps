"""补给箱冷却自注册/上次领取起计算，查询不重新计时。"""

import random

from config import Config
import utils.db as db
from utils.res_loader import res


def interval_seconds():
    row = next(
        (
            r
            for r in res["GlobalConfig"]["config"]["datas"]
            if r.get("key") == "SupplyBox_Random_Time"
        ),
        {},
    )
    values = row.get("values", ())
    low, high = (
        (int(values[0]), int(values[1]))
        if len(values) >= 2
        else Config.SUPPLY_BOX_COOLDOWN_MINUTES
    )
    return random.randint(min(low, high), max(low, high)) * 60


def next_reward_time(player_id):
    value = db.get_kv(player_id, "player", "supply_box_next")
    if value is None:
        created = db.get_players_info(player_id, "create_time")[0]
        value = int(created) + interval_seconds()
        db.set_kv(player_id, "player", "supply_box_next", value)
    return int(value)
