import concurrent.futures
import pickle
import random
import tempfile
import threading
import unittest
from pathlib import Path

from config import Config
import utils.db as db
import utils.res_loader as res_loader
from proto.net_pb2 import ItemDetail
from utils import item_mgr


class EconomyPropertyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        res_loader.init()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        db.exit()
        Config.DB_PATH = str(Path(self.tmp.name) / "economy.db")
        Config.IN_MEMORY = False
        db.init()
        db.db.execute(
            "INSERT INTO players(player_id, player_name, level, world_level, unlock_functions) "
            "VALUES (1, 'EconomyProperty', 10, 1, ?)",
            (pickle.dumps([]),),
        )

    def tearDown(self):
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory
        self.tmp.cleanup()

    def balance(self, item_id):
        return item_mgr.get_num(1, item_id)

    def set_balance(self, item_id, amount):
        detail = ItemDetail()
        detail.main_item.item_id = item_id
        detail.main_item.base_item.item_id = item_id
        detail.main_item.base_item.num = amount
        db.set_item_detail(1, detail.SerializeToString(), item_id)

    def test_random_grant_consume_sequence_conserves_balance(self):
        expected = {101: 500, 102: 500}
        item_mgr.grant_items(1, [(101, 500), (102, 500)])
        rng = random.Random(20261127)
        for step in range(600):
            item_id = rng.choice((101, 102))
            if rng.random() < 0.55:
                amount = rng.randint(1, 40)
                item_mgr.grant_items(1, [(item_id, amount)])
                expected[item_id] += amount
            else:
                amount = rng.randint(1, 60)
                ok = item_mgr.consume_items(1, [(item_id, amount)])
                self.assertEqual(ok, amount <= expected[item_id])
                if ok:
                    expected[item_id] -= amount
            if step % 30 == 0:
                self.assertGreaterEqual(self.balance(item_id), 0)
                self.assertEqual(self.balance(item_id), expected[item_id])
        self.assertEqual(self.balance(101), expected[101])
        self.assertEqual(self.balance(102), expected[102])

    def test_concurrent_consumption_never_overdraws(self):
        item_mgr.grant_items(1, [(101, 100)])
        barrier = threading.Barrier(20)

        def consume():
            barrier.wait()
            return item_mgr.consume_items(1, [(101, 1)])

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            results = [future.result() for future in [executor.submit(consume) for _ in range(20)]]
        self.assertEqual(sum(results), 20)
        self.assertEqual(self.balance(101), 80)

    def test_overflow_and_negative_grants_leave_balance_unchanged(self):
        limit = Config.ECONOMY_ITEM_NUM_MAX
        self.set_balance(101, limit)
        with self.assertRaises(item_mgr.EconomyConfigError):
            item_mgr.grant_items(1, [(101, 1)])
        self.assertEqual(self.balance(101), limit)
        with self.assertRaises(item_mgr.EconomyConfigError):
            item_mgr.grant_items(1, [(101, -1)])
        self.assertEqual(self.balance(101), limit)


if __name__ == "__main__":
    unittest.main()
