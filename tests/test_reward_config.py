import contextlib
import threading
import unittest
from unittest.mock import patch

from config import Config
from proto.net_pb2 import (
    ActivityRecallRewardClaimReq,
    DungeonData,
    DungeonStarRewardReq,
    StatusCode,
    SupplyBoxRewardReq,
)
import utils.db as db
from utils import item_mgr
import handlers.ActivityRecallRewardClaim as recall
import handlers.DungeonStarReward as dungeon
import handlers.SupplyBoxReward as supply


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class RewardConfigTests(unittest.TestCase):
    def test_recall_missing_config_rolls_back_claim(self):
        session = FakeSession()
        request = ActivityRecallRewardClaimReq(activity_id=1, condition_id=2)
        with patch.object(Config, 'ACTIVITY_RECALL_REWARDS', {}), \
             patch.object(recall.db, 'try_claim', return_value=True), \
             patch.object(recall.db, 'rollback_claim') as rollback, \
             patch.object(recall.db, 'grant_rewards') as grant:
            recall.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_CFG_NOT_FOUND)
        rollback.assert_called_once()
        grant.assert_not_called()

    def test_recall_uses_explicit_reward_config(self):
        session = FakeSession()
        request = ActivityRecallRewardClaimReq(activity_id=1, condition_id=2)
        with patch.object(Config, 'ACTIVITY_RECALL_REWARDS', {(1, 2): ((101, 5),)}), \
             patch.object(recall.db, 'try_claim', return_value=True), \
             patch.object(recall.db, 'grant_rewards') as grant, \
             patch.object(recall.achieve_track, 'report'):
            recall.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_OK)
        self.assertEqual(grant.call_args.args[1], ((101, 5),))

    def test_dungeon_star_missing_config_does_not_mark_claimed(self):
        session = FakeSession()
        request = DungeonStarRewardReq(dungeon_id=1001)
        with patch.object(Config, 'DUNGEON_STAR_REWARDS', {}), \
             patch.object(dungeon.db, 'get_dungeon', return_value=None), \
             patch.object(dungeon.db, 'set_dungeon') as save, \
             patch.object(dungeon.item_mgr, 'grant_items') as grant:
            dungeon.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_CFG_NOT_FOUND)
        save.assert_not_called()
        grant.assert_not_called()

    def test_supply_box_missing_config_has_no_side_effects(self):
        session = FakeSession()
        with patch.object(Config, 'SUPPLY_BOX_REWARDS', ()), \
             patch.object(supply.supply_box, 'next_reward_time') as cooldown, \
             patch.object(supply.item_mgr, 'grant_items') as grant:
            supply.Handler().handle(session, SupplyBoxRewardReq().SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_CFG_NOT_FOUND)
        cooldown.assert_not_called()
        grant.assert_not_called()

    def test_dungeon_star_uses_explicit_reward_config(self):
        session = FakeSession()
        request = DungeonStarRewardReq(dungeon_id=1001)
        progress = DungeonData(dungeon_id=1001, finish_times=1)
        with patch.object(Config, 'DUNGEON_STAR_REWARDS', {1001: ((102, 3),)}), \
             patch.object(dungeon.abyss, 'dungeon', return_value={'i_d': 1001}), \
             patch.object(dungeon.db, 'get_dungeon', return_value=progress.SerializeToString()), \
             patch.object(dungeon.db, 'set_dungeon') as save, \
             patch.object(dungeon.db, 'transaction', side_effect=contextlib.nullcontext), \
             patch.object(dungeon.db, 'try_claim', return_value=True), \
             patch.object(item_mgr, 'player_lock', return_value=threading.RLock()), \
             patch.object(dungeon.item_mgr, 'validate_rewards'), \
             patch.object(dungeon.item_mgr, 'grant_items') as grant:
            dungeon.Handler().handle(session, request.SerializeToString(), 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_OK)
        save.assert_called_once()
        self.assertEqual(grant.call_args.args[1], ((102, 3),))


if __name__ == '__main__':
    unittest.main(verbosity=2)
