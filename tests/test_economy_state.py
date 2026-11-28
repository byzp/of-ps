import contextlib
import threading
import unittest
from unittest.mock import patch

from config import Config
from proto.net_pb2 import GachaFullPickReq, GachaReq, ShopBuyReq, StatusCode
import handlers.Gacha as gacha
import handlers.GachaFullPick as full_pick
import handlers.ShopBuy as shop
import utils.db as db
from utils import item_mgr


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class EconomyStateTests(unittest.TestCase):
    def test_negative_shop_quantity_is_rejected(self):
        session = FakeSession()
        with patch.object(shop.db, 'get_players_info', return_value=[1]), \
             patch.object(shop.item_mgr, 'grant_items') as grant:
            shop.Handler().handle(session, ShopBuyReq(shop_id=100, grid_id=1, buy_times=Config.MAX_SHOP_BUY_TIMES + 1).SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_BAD_REQ)
        grant.assert_not_called()

    def test_invalid_gacha_pool_does_not_consume(self):
        session = FakeSession()
        with patch.object(gacha, '_configuration', return_value=None), \
             patch.object(gacha.item_mgr, 'consume_items') as consume:
            gacha.Handler().handle(session, GachaReq(gacha_id=999999, is_single=True).SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_CFG_NOT_FOUND)
        consume.assert_not_called()

    def test_gacha_guarantee_pool_is_used_at_threshold(self):
        session = FakeSession()
        info = {'max_times': 50, 'consume_item1_i_d': 104, 'method1_count': 1, 'consume_item1_num': 1}
        with patch.object(gacha, '_configuration', return_value=(info, [101], [102])), \
             patch.object(db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(item_mgr, 'player_lock', return_value=threading.RLock()), \
             patch.object(item_mgr, 'consume_items', return_value=True), \
             patch.object(item_mgr, 'grant_single_item') as grant, \
             patch.object(db, 'get_gacha_guarantee', return_value=49), \
             patch.object(db, 'set_gacha_guarantee') as set_guarantee, \
             patch.object(db, 'add_gacha_record'), \
             patch.object(db, 'get_total_gacha_num', return_value=1), \
             patch.object(gacha.random, 'choice', side_effect=lambda values: values[0]), \
             patch.object(gacha.achieve_track, 'report'):
            gacha.Handler().handle(session, GachaReq(gacha_id=1000, is_single=True).SerializeToString(), 1)
        self.assertEqual(grant.call_args.args[1], 102)
        set_guarantee.assert_called_once_with(1, 1000, 0)

    def test_full_pick_cannot_be_claimed_twice(self):
        session = FakeSession()
        with patch.object(full_pick, '_configuration', return_value=({}, [101], [])), \
             patch.object(db, 'get_total_gacha_num', return_value=Config.FULL_PICK_MIN_DRAWS), \
             patch.object(db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(item_mgr, 'player_lock', return_value=threading.RLock()), \
             patch.object(db, 'try_claim', return_value=False), \
             patch.object(item_mgr, 'grant_single_item') as grant:
            full_pick.Handler().handle(session, GachaFullPickReq(gacha_id=1000, item_id=101).SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_REPEAT_GET_REWARD)
        grant.assert_not_called()

    def test_full_pick_rejects_item_outside_pool(self):
        session = FakeSession()
        with patch.object(full_pick, '_configuration', return_value=({}, [101], [])), \
             patch.object(db, 'get_total_gacha_num', return_value=Config.FULL_PICK_MIN_DRAWS), \
             patch.object(item_mgr, 'grant_single_item') as grant:
            full_pick.Handler().handle(session, GachaFullPickReq(gacha_id=1000, item_id=999999).SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_GACHA_ITEM_NOT_EXIST)
        grant.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
