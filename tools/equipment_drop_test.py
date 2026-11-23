"""核对真实装备资源及各随机掉落入口的完整候选池，不连接玩家数据库。"""

from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import db, res_loader
from utils import dungeon_reward, monster_loot, pb_create
from utils.equipment_pool import random_equipment_ids
from proto.net_pb2 import ItemDetail


class EquipmentDropTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res_loader.init()
        random_equipment_ids.cache_clear()
        cls.items = {row["i_d"]: row for row in res_loader.res["Item"]["item"]["datas"]}

    def test_unfinished_and_test_equipment_excluded(self):
        allowed = random_equipment_ids()
        self.assertTrue({1101101, 1201104, 1402202, 2121006} <= allowed)
        self.assertFalse(
            {1000001, 1000010, 1101107, 2111008, 1104306, 1104310} & allowed
        )
        icons = {row["i_d"]: row for row in res_loader.res["UI"]["icon"]["datas"]}
        for item_id in allowed:
            paths = icons[self.items[item_id]["icon_i_d"]]["asset_full_name"]
            self.assertTrue(paths)
            self.assertTrue(
                all(path and not path.endswith(("/", "\\")) for path in paths)
            )

    def test_all_random_equipment_candidates(self):
        allowed = random_equipment_ids()
        sampled = set()
        original_choice = random.choice

        def choose(candidates):
            equipment = {
                item_id
                for item_id in candidates
                if self.items.get(item_id, {}).get("new_bag_item_tag") in (2, 3)
            }
            self.assertTrue(equipment <= allowed, equipment - allowed)
            sampled.update(equipment)
            return original_choice(candidates)

        def make_item(item_id, count=1, player_id=0, **kwargs):
            detail = ItemDetail()
            detail.main_item.item_id = item_id
            tag = self.items[item_id].get("new_bag_item_tag")
            if tag == 2:
                detail.main_item.weapon.weapon_id = item_id
            elif tag == 3:
                detail.main_item.armor.armor_id = item_id
            else:
                detail.main_item.base_item.num = count
            return detail

        with (
            patch.object(db, "get_players_info", return_value=(100,)),
            patch.object(pb_create, "make_item", side_effect=make_item),
            patch.object(monster_loot, "make_item", side_effect=make_item),
            patch.object(dungeon_reward, "make_item", side_effect=make_item),
            patch.object(random, "choice", side_effect=choose),
            patch.object(random, "random", return_value=0.0),
        ):
            for world_level in range(1, 6):
                for _ in range(10):
                    pb_create.make_treasure_box_item(1, world_level, num=10)
                    monster_loot.roll(1, 100, world_level)
            for cfg in res_loader.res["Dungeon"]["dungeon"]["datas"]:
                dungeon_reward.make_dungeon_rewards(1, cfg)
        self.assertTrue(sampled)
        self.assertTrue(any(self.items[i]["new_bag_item_tag"] == 2 for i in sampled))
        self.assertTrue(any(self.items[i]["new_bag_item_tag"] == 3 for i in sampled))


if __name__ == "__main__":
    unittest.main()
