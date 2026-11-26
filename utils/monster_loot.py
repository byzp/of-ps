"""普通怪本地掉落策略；有明确奖励池的怪物仍使用原池。"""

import random

from config import Config
from proto.net_pb2 import ItemDetail
from utils.pb_create import make_item
from utils.res_loader import res
from utils.equipment_pool import random_equipment_ids


def roll(player_id, player_level, world_level):
    if random.random() >= Config.NORMAL_MONSTER_DROP_CHANCE:
        return []
    equipment = random_equipment_ids()
    material_ids = {
        row["get_item_i_d"]
        for row in res["Spin"]["spin_item"]["datas"]
        if row.get("spin_level") == 1
        and row.get("new_spin_type") == Config.NORMAL_MONSTER_MATERIAL_SPIN_TYPE
    }
    pools = {}
    for row in res["Item"]["item"]["datas"]:
        item_id = row["i_d"]
        tag = row.get("new_bag_item_tag")
        if tag in (2, 3) and item_id not in equipment:
            continue
        if tag == 8 and item_id not in material_ids:
            continue
        if tag in (2, 3) and row.get("quality", 0) > max(1, world_level):
            continue
        if tag in (2, 3, 8):
            pools.setdefault(tag, []).append(item_id)
    categories = [
        (tag, weight)
        for tag, weight in Config.NORMAL_MONSTER_DROP_WEIGHTS
        if pools.get(tag)
    ]
    if not categories:
        return []
    world = next(
        (
            r
            for r in res["Level"]["world_level"]["datas"]
            if r["i_d"] == max(1, world_level)
        ),
        {},
    )
    maximum_level = max(1, min(player_level, world.get("monster_level", player_level)))
    items = []
    for _ in range(random.randint(*Config.NORMAL_MONSTER_DROP_COUNT)):
        tag = random.choices(
            [tag for tag, _ in categories], weights=[weight for _, weight in categories]
        )[0]
        item_id = random.choice(pools[tag])
        count = random.randint(*Config.NORMAL_MONSTER_MATERIAL_COUNT) if tag == 8 else 1
        level = random.randint(1, maximum_level) if tag in (2, 3) else None
        item = make_item(item_id, count, player_id, equipment_level=level)
        item.pack_type = ItemDetail.PackType.PackType_TempStorageArea
        items.append(item)
    return items
