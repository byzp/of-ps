import concurrent.futures
import contextlib
import pickle
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config import Config
# 先加载 db, 保持项目既有 protobuf 工具循环导入顺序。
import utils.db as db
import utils.res_loader as res_loader
from utils import item_mgr
from network.msg_id import MsgId
from proto.net_pb2 import (
    ClaimQuestRewardReq,
    DungeonData,
    DungeonFinishReq,
    ItemDetail,
    ExploreCollectRewardReq,
    ExploreQuickFinishReq,
    ExploreReq,
    ExploreRewardReq,
    FishingReq,
    GachaFullPickReq,
    GachaReq,
    GatherReq,
    ItemUseReq,
    Quest,
    QuestStatus,
    ShopBuyReq,
    StatusCode,
)
import handlers.ClaimQuestReward as claim
import handlers.DungeonFinish as dungeon_finish
import handlers.Explore as explore
import handlers.ExploreCollectReward as explore_collect
import handlers.ExploreQuickFinish as explore_quick
import handlers.ExploreReward as explore_reward
import handlers.Fishing as fishing
import handlers.Gacha as gacha
import handlers.GachaFullPick as full_pick
import handlers.Gather as gather
import handlers.ItemUse as item_use
import handlers.ShopBuy as shop
import utils.garden_state as garden_state


class FakeSession:
    def __init__(self, player_id=1, scene_id=1, channel_id=1):
        self.player_id = player_id
        self.player_name = "EconomyTest"
        self.scene_id = scene_id
        self.channel_id = channel_id
        self.running = True
        self.fishing = False
        self.fishing_token = ""
        self.fishing_cost = None
        self.dungeon = [0, 0, 0, -1]
        self.dungeon_token = ""
        self.quests = {}
        self.temp_pack = []
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))

    def response(self, message_id):
        return [message for mid, message, _ in self.sent if mid == message_id][-1]


class EconomyConcurrencyTests(unittest.TestCase):
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
            "INSERT INTO players(player_id, player_name, level, world_level, unlock_functions) VALUES (1, 'EconomyTest', 10, 1, ?)",
            (pickle.dumps([]),),
        )
        self.report_patch = patch.object(item_mgr.achieve_track, "report")
        self.report_patch.start()

    def tearDown(self):
        self.report_patch.stop()
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory
        self.tmp.cleanup()

    def grant(self, item_id, count, player_id=1):
        item_mgr.grant_items(player_id, [(item_id, count)])

    def num(self, item_id, player_id=1):
        return item_mgr.get_num(player_id, item_id)

    def concurrently(self, calls):
        barrier = threading.Barrier(len(calls))

        def invoke(call):
            barrier.wait()
            return call()

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls)) as executor:
            return [future.result() for future in [executor.submit(invoke, call) for call in calls]]

    @staticmethod
    def shop_resources(price=10, costs=None, item_id=104, item_num=1, limit=1):
        costs = costs if costs is not None else [{"currency_i_d": 101, "price": price}]
        return {
            "Shop": {
                "grid": {"datas": [{
                    "i_d": 1,
                    "items": [{"grid_i_d": 1, "shop_pool_i_d": 2, "buy_max_count": limit}],
                }]},
                "pool": {"datas": [{
                    "i_d": 2,
                    "items": [{
                        "index": 1,
                        "item_i_d": item_id,
                        "item_num": item_num,
                        "shop_currency_item": costs,
                    }],
                }]},
                "increasing": {"datas": []},
            }
        }

    @staticmethod
    def gacha_resources(cap=2):
        return {
            "Gacha": {
                "info": {"datas": [{
                    "i_d": 10,
                    "max_times": cap,
                    "big_guarantee_pool_i_d": 22,
                    "consume_item1_i_d": 104,
                    "method1_count": 1,
                    "consume_item1_num": 1,
                    "consume_item2_i_d": 104,
                    "consume_item2_num": 10,
                }]},
                "pool": {"datas": [{"i_d": 10, "items": [{"free_gacha_pool_i_d": 21}]}]},
                "reward_pool": {"datas": [
                    {"i_d": 21, "items": [{"item_i_d": 101}]},
                    {"i_d": 22, "items": [{"item_i_d": 102}]},
                ]},
            }
        }

    def buy(self, session=None, times=1):
        session = session or FakeSession()
        shop.Handler().handle(
            session, ShopBuyReq(shop_id=1, grid_id=1, buy_times=times).SerializeToString(), 1
        )
        return session.response(MsgId.ShopBuyRsp)

    def test_concurrent_limited_purchase_debits_and_grants_once(self):
        self.grant(101, 100)
        sessions = [FakeSession() for _ in range(8)]
        with patch.dict(res_loader.res, self.shop_resources()):
            statuses = self.concurrently([
                (lambda session=session: self.buy(session).status) for session in sessions
            ])
        self.assertEqual(statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(statuses.count(StatusCode.StatusCode_SHOP_GRID_BUY_NUM_LIMIT), 7)
        self.assertEqual(self.num(101), 90)
        self.assertEqual(self.num(104), 1)
        self.assertEqual(db.get_kv(1, "shop_buy", "2:p"), 1)

    def test_concurrent_unlimited_purchases_do_not_lose_balance_updates(self):
        self.grant(101, 100)
        sessions = [FakeSession() for _ in range(5)]
        with patch.dict(res_loader.res, self.shop_resources(limit=-1)):
            statuses = self.concurrently([
                (lambda session=session: self.buy(session).status) for session in sessions
            ])
        self.assertEqual(statuses, [StatusCode.StatusCode_OK] * 5)
        self.assertEqual(self.num(101), 50)
        self.assertEqual(self.num(104), 5)
        self.assertEqual(db.get_kv(1, "shop_buy", "2:p"), 5)

    def test_unique_outfit_reward_is_stored_once(self):
        self.grant(4100292, 1)
        blob = db.get_item_detail(1, 4100292)
        self.assertTrue(blob)
        detail = ItemDetail()
        detail.ParseFromString(blob)
        self.assertEqual(detail.main_item.WhichOneof("item"), "outfit")
        self.assertEqual(detail.main_item.outfit.outfit_id, 4100292)

        # 重复发放同一件时装必须幂等，不能造出第二件或抛异常。
        self.grant(4100292, 1)
        self.assertEqual(db.get_item_detail(1, 4100292), blob)

    def test_insufficient_multi_currency_cost_rolls_back_every_balance(self):
        self.grant(101, 10)
        self.grant(102, 4)
        resources = self.shop_resources(costs=[
            {"currency_i_d": 101, "price": 10},
            {"currency_i_d": 102, "price": 5},
        ])
        with patch.dict(res_loader.res, resources):
            rsp = self.buy()
        self.assertEqual(rsp.status, StatusCode.StatusCode_ITEM_NOT_ENOUGH)
        self.assertEqual((self.num(101), self.num(102), self.num(104)), (10, 4, 0))
        self.assertIsNone(db.get_kv(1, "shop_buy", "2:p"))

    def test_star_currency_fallback_is_atomic_and_never_negative(self):
        self.grant(102, 2)
        self.grant(108, 5)
        resources = self.shop_resources(costs=[{"currency_i_d": 102, "price": 4}])
        with patch.dict(res_loader.res, resources):
            rsp = self.buy()
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual((self.num(102), self.num(108), self.num(104)), (0, 3, 1))

        resources = self.shop_resources(costs=[{"currency_i_d": 102, "price": 4}], limit=-1)
        with patch.dict(res_loader.res, resources):
            rsp = self.buy()
        self.assertEqual(rsp.status, StatusCode.StatusCode_ITEM_NOT_ENOUGH)
        self.assertEqual((self.num(102), self.num(108), self.num(104)), (0, 3, 1))

    def test_grant_failure_after_payment_rolls_back_debit_and_purchase_count(self):
        self.grant(101, 10)
        with patch.dict(res_loader.res, self.shop_resources(limit=-1)), \
             patch.object(item_mgr, "grant_items", side_effect=RuntimeError("synthetic grant failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                self.buy()
        self.assertEqual((self.num(101), self.num(104)), (10, 0))
        self.assertIsNone(db.get_kv(1, "shop_buy", "2:p"))
        with patch.dict(res_loader.res, self.shop_resources(limit=-1)):
            self.assertEqual(self.buy().status, StatusCode.StatusCode_OK)

    def test_missing_product_config_and_overflow_are_rejected_before_payment(self):
        self.grant(101, 100)
        with patch.dict(res_loader.res, self.shop_resources(item_id=999999999)):
            self.assertEqual(self.buy().status, StatusCode.StatusCode_CFG_NOT_FOUND)
        with patch.dict(res_loader.res, self.shop_resources(price=Config.ECONOMY_ITEM_NUM_MAX, limit=-1)):
            self.assertEqual(self.buy(times=2).status, StatusCode.StatusCode_CFG_NOT_FOUND)
        self.assertEqual((self.num(101), self.num(104)), (100, 0))
        self.assertIsNone(db.get_kv(1, "shop_buy", "2:p"))

    def test_item_manager_validates_entire_batch_and_balance_overflow(self):
        self.grant(101, 5)
        with self.assertRaises(item_mgr.EconomyConfigError):
            item_mgr.grant_items(1, [(101, 1), (102, -1)])
        self.assertEqual((self.num(101), self.num(102)), (5, 0))
        with self.assertRaises(item_mgr.EconomyConfigError):
            item_mgr.grant_items(1, [(999999999, 1)])
        detail = item_mgr.grant_single_item(1, 101, Config.ECONOMY_ITEM_NUM_MAX - 5)
        self.assertEqual(detail.main_item.base_item.num, Config.ECONOMY_ITEM_NUM_MAX)
        with self.assertRaises(item_mgr.EconomyConfigError):
            item_mgr.grant_single_item(1, 101, 1)
        self.assertEqual(self.num(101), Config.ECONOMY_ITEM_NUM_MAX)

    def test_fishing_cancel_refunds_once_and_invalidates_timer(self):
        self.grant(11, 5)
        session = FakeSession()
        timer = Mock()
        with patch.object(fishing, "_fishing_level", return_value=1), \
             patch.object(fishing, "_cast_cost", return_value=(11, 1)), \
             patch.object(fishing.random, "random", return_value=1), \
             patch.object(fishing.threading, "Timer", return_value=timer):
            fishing.Handler().handle(session, FishingReq().SerializeToString(), 1)
            self.assertEqual(session.response(MsgId.FishingRsp).status, StatusCode.StatusCode_OK)
            self.assertEqual(self.num(11), 4)
            token = session.fishing_token
            fishing.Handler().handle(session, FishingReq(is_cancel=True).SerializeToString(), 2)
            fishing.Handler().handle(session, FishingReq(is_cancel=True).SerializeToString(), 3)
        self.assertEqual(self.num(11), 5)
        self.assertFalse(session.fishing)
        self.assertEqual(session.fishing_token, "")
        fishing.Handler._finish(session, token, 0, None)
        self.assertEqual(self.num(11), 5)
        self.assertEqual(session.response(MsgId.FishingRsp).is_cancel, True)

    def test_fishing_cancel_finish_race_never_refunds_and_pays(self):
        for _ in range(12):
            if self.num(11):
                item_mgr.consume_items(1, [(11, self.num(11))])
            if self.num(101):
                item_mgr.consume_items(1, [(101, self.num(101))])
            self.grant(11, 1)
            session = FakeSession()
            timer = Mock()
            with patch.object(fishing, "_fishing_level", return_value=1), \
                 patch.object(fishing, "_cast_cost", return_value=(11, 1)), \
                 patch.object(fishing.random, "random", return_value=1), \
                 patch.object(fishing.threading, "Timer", return_value=timer):
                fishing.Handler().handle(session, FishingReq().SerializeToString(), 1)
            token = session.fishing_token
            barrier = threading.Barrier(2)

            def cancel():
                barrier.wait()
                fishing.Handler._cancel(session, 2)

            def finish():
                barrier.wait()
                fishing.Handler._finish(session, token, 101, {})

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(cancel), executor.submit(finish)]
                for future in futures:
                    future.result()
            self.assertIn((self.num(11), self.num(101)), ((1, 0), (0, 1)))

    def test_fishing_timer_start_failure_refunds_reserved_energy(self):
        self.grant(11, 1)
        timer = Mock()
        timer.start.side_effect = RuntimeError("timer failed")
        with patch.object(fishing, "_fishing_level", return_value=1), \
             patch.object(fishing, "_cast_cost", return_value=(11, 1)), \
             patch.object(fishing.random, "random", return_value=1), \
             patch.object(fishing.threading, "Timer", return_value=timer):
            with self.assertRaisesRegex(RuntimeError, "timer failed"):
                fishing.Handler().handle(FakeSession(), FishingReq().SerializeToString(), 1)
        self.assertEqual(self.num(11), 1)

    def test_concurrent_gacha_at_pity_threshold_grants_exactly_one_guarantee(self):
        self.grant(104, 2)
        db.set_gacha_guarantee(1, 10, 1)
        sessions = [FakeSession() for _ in range(2)]
        with patch.dict(res_loader.res, self.gacha_resources(cap=2)), \
             patch.object(gacha.random, "choice", side_effect=lambda values: values[0]):
            statuses = self.concurrently([
                (lambda session=session: gacha.Handler().handle(
                    session, GachaReq(gacha_id=10, is_single=True).SerializeToString(), 1
                )) for session in sessions
            ])
        responses = [session.response(MsgId.GachaRsp) for session in sessions]
        self.assertEqual([rsp.status for rsp in responses], [StatusCode.StatusCode_OK] * 2)
        rewards = [item.main_item.item_id for rsp in responses for item in rsp.items]
        self.assertEqual(rewards.count(101), 1)
        self.assertEqual(rewards.count(102), 1)
        self.assertEqual((self.num(104), self.num(101), self.num(102)), (0, 1, 1))
        self.assertEqual(db.get_gacha_guarantee(1, 10), 1)
        self.assertEqual(db.get_total_gacha_num(1, 10), 2)

    def test_ten_pull_applies_pity_to_every_draw(self):
        self.grant(104, 10)
        session = FakeSession()
        with patch.dict(res_loader.res, self.gacha_resources(cap=3)), \
             patch.object(gacha.random, "choice", side_effect=lambda values: values[0]):
            gacha.Handler().handle(session, GachaReq(gacha_id=10, is_single=False).SerializeToString(), 1)
        rsp = session.response(MsgId.GachaRsp)
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        rewards = [item.main_item.item_id for item in rsp.items]
        self.assertEqual((rewards.count(101), rewards.count(102)), (7, 3))
        self.assertEqual(db.get_gacha_guarantee(1, 10), 1)
        self.assertEqual(self.num(104), 0)

    def test_concurrent_full_pick_claims_selected_item_once(self):
        db.add_gacha_record(1, 10, 101)
        sessions = [FakeSession() for _ in range(8)]
        with patch.dict(res_loader.res, self.gacha_resources()), \
             patch.object(Config, "FULL_PICK_MIN_DRAWS", 1):
            statuses = self.concurrently([
                (lambda session=session: full_pick.Handler().handle(
                    session, GachaFullPickReq(gacha_id=10, item_id=101).SerializeToString(), 1
                )) for session in sessions
            ])
        responses = [session.response(MsgId.GachaFullPickRsp) for session in sessions]
        self.assertEqual([rsp.status for rsp in responses].count(StatusCode.StatusCode_OK), 1)
        self.assertEqual([rsp.status for rsp in responses].count(StatusCode.StatusCode_REPEAT_GET_REWARD), 7)
        self.assertEqual(self.num(101), 1)
        self.assertEqual(db.get_total_gacha_num(1, 10), 2)

    def test_concurrent_quest_reward_includes_first_reward_once(self):
        quest = Quest(quest_id=900001, status=QuestStatus.QuestStatus_Finish)
        db.set_quest(1, 900001, quest.SerializeToString())
        sessions = [FakeSession() for _ in range(8)]
        resources = {"Quest": {"quest": {"datas": [{
            "i_d": 900001, "reward": 1, "first_reward": 2, "limit_num": 1,
        }]}}}
        with patch.dict(res_loader.res, resources), \
             patch.object(claim._qt, "is_completed_live", return_value=True), \
             patch.object(claim, "resolve_reward", side_effect=lambda reward_id, level: [(101, 5)]):
            statuses = self.concurrently([
                (lambda session=session: claim.Handler().handle(
                    session, ClaimQuestRewardReq(quest_id=900001).SerializeToString(), 1
                )) for session in sessions
            ])
        responses = [session.response(MsgId.ClaimQuestRewardRsp) for session in sessions]
        self.assertEqual([rsp.status for rsp in responses].count(StatusCode.StatusCode_OK), 1)
        self.assertEqual([rsp.status for rsp in responses].count(StatusCode.StatusCode_REPEAT_GET_REWARD), 7)
        self.assertEqual(self.num(101), 10)
        self.assertEqual(Quest.FromString(db.get_quest(1, 900001)).complete_count, 1)

    def test_concurrent_story_reward_marks_chapter_once(self):
        sessions = [FakeSession() for _ in range(8)]
        resources = {"Story": {
            "story_chapter": {"datas": [{"i_d": 1, "story_list": [900001]}]},
            "story": {"datas": [{"i_d": 900001, "quest_i_d": 900002, "reward": 1}]},
        }}
        with patch.dict(res_loader.res, resources), \
             patch.object(claim._qt, "is_completed_live", return_value=True), \
             patch.object(claim, "_chain_tail_echo", return_value=Quest(quest_id=900002, complete_count=1)), \
             patch.object(claim, "resolve_reward", return_value=[(102, 2)]):
            statuses = self.concurrently([
                (lambda session=session: claim.Handler().handle(
                    session, ClaimQuestRewardReq(quest_id=900001).SerializeToString(), 1
                )) for session in sessions
            ])
        responses = [session.response(MsgId.ClaimQuestRewardRsp) for session in sessions]
        self.assertEqual([rsp.status for rsp in responses].count(StatusCode.StatusCode_OK), 1)
        self.assertEqual([rsp.status for rsp in responses].count(StatusCode.StatusCode_REPEAT_GET_REWARD), 7)
        self.assertEqual(self.num(102), 2)
        self.assertIn(900001, claim.Chapter.FromString(db.get_chapter(1, 1)).rewarded_story_ids)

    def test_missing_quest_reward_config_does_not_consume_claim(self):
        quest = Quest(quest_id=900001, status=QuestStatus.QuestStatus_Finish)
        db.set_quest(1, 900001, quest.SerializeToString())
        resources = {"Quest": {"quest": {"datas": [{
            "i_d": 900001, "reward": 987654, "limit_num": 1,
        }]}}}
        session = FakeSession()
        with patch.dict(res_loader.res, resources), \
             patch.object(claim._qt, "is_completed_live", return_value=True), \
             patch.object(claim, "resolve_reward", return_value=[]):
            claim.Handler().handle(session, ClaimQuestRewardReq(quest_id=900001).SerializeToString(), 1)
        self.assertEqual(session.response(MsgId.ClaimQuestRewardRsp).status, StatusCode.StatusCode_CFG_NOT_FOUND)
        self.assertEqual(Quest.FromString(db.get_quest(1, 900001)).complete_count, 0)
        self.assertEqual(self.num(101), 0)

    def test_explore_quick_finish_reward_and_collect_are_each_atomic(self):
        self.grant(102, 1)
        start = FakeSession()
        explore.Handler().handle(start, ExploreReq(explore_id=10101).SerializeToString(), 1)
        self.assertEqual(start.response(MsgId.ExploreRsp).status, StatusCode.StatusCode_OK)
        quick_sessions = [FakeSession() for _ in range(8)]
        quick_statuses = self.concurrently([
            (lambda session=session: self._quick(session)) for session in quick_sessions
        ])
        self.assertEqual(quick_statuses.count(StatusCode.StatusCode_OK), 8)
        self.assertEqual(self.num(102), 0)
        self.assertTrue(garden_state.get_explore(1, 10101)["is_quick_finish"])

        reward_sessions = [FakeSession() for _ in range(8)]
        reward_statuses = self.concurrently([
            (lambda session=session: self._explore_reward(session)) for session in reward_sessions
        ])
        self.assertEqual(reward_statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(reward_statuses.count(StatusCode.StatusCode_EXPLORE_NOT_FINISH), 7)
        self.assertEqual((self.num(101), self.num(109)), (10, 10))
        self.assertEqual(garden_state.get_explore(1, 10101)["times"], 1)

        collect_sessions = [FakeSession() for _ in range(8)]
        collect_statuses = self.concurrently([
            (lambda session=session: self._explore_collect(session)) for session in collect_sessions
        ])
        self.assertEqual(collect_statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(collect_statuses.count(StatusCode.StatusCode_REPEAT_GET_REWARD), 7)
        self.assertEqual((self.num(101), self.num(109)), (15, 15))

    @staticmethod
    def _quick(session):
        explore_quick.Handler().handle(
            session, ExploreQuickFinishReq(explore_id=10101).SerializeToString(), 1
        )
        return session.response(MsgId.ExploreQuickFinishRsp).status

    @staticmethod
    def _explore_reward(session):
        explore_reward.Handler().handle(
            session, ExploreRewardReq(explore_id=10101).SerializeToString(), 1
        )
        return session.response(MsgId.ExploreRewardRsp).status

    @staticmethod
    def _explore_collect(session):
        explore_collect.Handler().handle(
            session, ExploreCollectRewardReq(explore_id=10101).SerializeToString(), 1
        )
        return session.response(MsgId.ExploreCollectRewardRsp).status

    def test_explore_missing_rewards_and_grant_failure_preserve_state(self):
        state = garden_state.get_explore(1, 10101)
        state["start_time"] = 1
        garden_state.set_explore(1, 10101, state)
        valid_cfg = garden_state.explore_area_cfg(10101)
        cfg = dict(valid_cfg)
        cfg["explore_area_item"] = ()
        with patch.object(garden_state, "explore_area_cfg", return_value=cfg):
            session = FakeSession()
            self._explore_collect(session)
            self.assertEqual(session.response(MsgId.ExploreCollectRewardRsp).status, StatusCode.StatusCode_CFG_NOT_FOUND)
            self.assertFalse(garden_state.get_explore(1, 10101)["collect_reward"])
            self.assertEqual((self.num(101), self.num(109)), (0, 0))
            with patch.object(garden_state, "explore_area_cfg", return_value=valid_cfg), \
                 patch.object(item_mgr, "grant_items", side_effect=RuntimeError("synthetic")):
                with self.assertRaisesRegex(RuntimeError, "synthetic"):
                    self._explore_reward(FakeSession())
        self.assertEqual(garden_state.get_explore(1, 10101)["start_time"], 1)
        self.assertEqual(garden_state.get_explore(1, 10101)["times"], 0)

    def test_concurrent_gather_same_point_pays_once(self):
        request = GatherReq()
        request.gather_item.index = 3
        request.gather_item.reward = res_loader.res["Gather"]["gather_reward"]["datas"][0]["i_d"]
        sessions = [FakeSession() for _ in range(8)]
        with patch.object(gather, "make_Achieve"):
            statuses = self.concurrently([
                (lambda session=session: self._gather(session, request)) for session in sessions
            ])
        self.assertEqual(statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(statuses.count(StatusCode.StatusCode_GATHER_LIMIT), 7)
        keys = db.get_kv_keys(1, "gather_daily")
        self.assertEqual(len(keys), 1)
        self.assertEqual(db.get_kv(1, "gather_daily", keys[0]), 1)

    @staticmethod
    def _gather(session, request):
        gather.Handler().handle(session, request.SerializeToString(), 1)
        return session.response(MsgId.GatherRsp).status

    def test_concurrent_item_use_cannot_overspend_restore_item(self):
        item_id = next(
            row["i_d"] for row in res_loader.res["Item"]["item"]["datas"]
            if row.get("new_bag_item_tag") == 32 and int(row.get("relate_i_d", 0) or 0) > 0
        )
        relate = next(
            int(row["relate_i_d"]) for row in res_loader.res["Item"]["item"]["datas"]
            if row["i_d"] == item_id
        )
        self.grant(item_id, 3)
        sessions = [FakeSession() for _ in range(2)]
        resources = {
            "Reward": {"reward_pool": {"datas": []}, "reward_item_pool": {"datas": []}},
            "Expression": {"catcher": {"datas": []}},
        }
        with patch.dict(res_loader.res, resources):
            statuses = self.concurrently([
                (lambda session=session: self._use(session, item_id, 2)) for session in sessions
            ])
        self.assertEqual(statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(statuses.count(StatusCode.StatusCode_ITEM_NOT_ENOUGH), 1)
        self.assertEqual(self.num(item_id), 1)
        self.assertEqual(self.num(10), relate * 2)

    @staticmethod
    def _use(session, item_id, count):
        item_use.Handler().handle(session, ItemUseReq(item_id=item_id, num=count).SerializeToString(), 1)
        return session.response(MsgId.ItemUseRsp).status

    def test_zero_item_use_and_missing_reward_group_have_no_side_effects(self):
        item_id = next(
            row["i_d"] for row in res_loader.res["Item"]["item"]["datas"]
            if row.get("new_bag_item_tag") == 32 and int(row.get("relate_i_d", 0) or 0) > 0
        )
        self.grant(item_id, 2)
        self.assertEqual(self._use(FakeSession(), item_id, 0), StatusCode.StatusCode_BAD_REQ)
        resources = {"Reward": {
            "reward_pool": {"datas": [{"i_d": item_id, "reward_pool_group": [{"reward_pool_group_i_d": 999999}]}]},
            "reward_item_pool": {"datas": []},
        }}
        with patch.dict(res_loader.res, resources):
            self.assertEqual(self._use(FakeSession(), item_id, 1), StatusCode.StatusCode_CFG_NOT_FOUND)
        self.assertEqual(self.num(item_id), 2)
        self.assertEqual(self.num(10), 0)

    def test_item_use_grant_failure_rolls_back_consumed_item(self):
        item_id = next(
            row["i_d"] for row in res_loader.res["Item"]["item"]["datas"]
            if row.get("new_bag_item_tag") == 32 and int(row.get("relate_i_d", 0) or 0) > 0
        )
        self.grant(item_id, 2)
        resources = {
            "Reward": {"reward_pool": {"datas": []}, "reward_item_pool": {"datas": []}},
            "Expression": {"catcher": {"datas": []}},
        }
        with patch.dict(res_loader.res, resources), \
             patch.object(item_mgr, "grant_items", side_effect=RuntimeError("synthetic")):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                self._use(FakeSession(), item_id, 1)
        self.assertEqual((self.num(item_id), self.num(10)), (2, 0))

    def test_concurrent_dungeon_finish_grants_first_clear_once_per_run(self):
        dungeon = DungeonData(dungeon_id=1001, finish_times=0)
        db.set_dungeon(1, 1001, dungeon.SerializeToString())
        sessions = [FakeSession() for _ in range(8)]
        for session in sessions:
            session.dungeon = [1001, 0, 0, -1]
            session.dungeon_token = "run-1"
        with patch.object(dungeon_finish, "dungeon_config", return_value={"i_d": 1001, "reward_i_d": 1}), \
             patch.object(dungeon_finish, "resolve_drop", return_value=[(101, 7)]):
            statuses = self.concurrently([
                (lambda session=session: self._finish_dungeon(session)) for session in sessions
            ])
        self.assertEqual(statuses.count(StatusCode.StatusCode_OK), 1)
        self.assertEqual(statuses.count(StatusCode.StatusCode_REPEAT_GET_REWARD), 7)
        self.assertEqual(self.num(101), 7)
        self.assertEqual(DungeonData.FromString(db.get_dungeon(1, 1001)).finish_times, 1)
        self.assertTrue(db.has_claimed(1, "dungeon_finish", "run-1"))

        second = FakeSession()
        second.dungeon = [1001, 0, 0, -1]
        second.dungeon_token = "run-2"
        with patch.object(dungeon_finish, "dungeon_config", return_value={"i_d": 1001, "reward_i_d": 1}), \
             patch.object(dungeon_finish, "resolve_drop", return_value=[(101, 7)]):
            self.assertEqual(self._finish_dungeon(second), StatusCode.StatusCode_OK)
        self.assertEqual(self.num(101), 7)
        self.assertEqual(DungeonData.FromString(db.get_dungeon(1, 1001)).finish_times, 2)

    @staticmethod
    def _finish_dungeon(session):
        dungeon_finish.Handler().handle(session, DungeonFinishReq().SerializeToString(), 1)
        return session.response(MsgId.DungeonFinishRsp).status

    def test_dungeon_missing_config_or_grant_failure_rolls_back_first_clear(self):
        dungeon = DungeonData(dungeon_id=1001, finish_times=0)
        db.set_dungeon(1, 1001, dungeon.SerializeToString())
        session = FakeSession()
        session.dungeon = [1001, 0, 0, -1]
        session.dungeon_token = "run-failure"
        with patch.object(dungeon_finish, "dungeon_config", return_value=None):
            self.assertEqual(self._finish_dungeon(session), StatusCode.StatusCode_CFG_NOT_FOUND)
        self.assertFalse(db.has_claimed(1, "dungeon_finish", "run-failure"))
        self.assertEqual(DungeonData.FromString(db.get_dungeon(1, 1001)).finish_times, 0)
        with patch.object(dungeon_finish, "dungeon_config", return_value={"i_d": 1001, "reward_i_d": 1}), \
             patch.object(dungeon_finish, "resolve_drop", return_value=[(101, 7)]), \
             patch.object(item_mgr, "grant_items", side_effect=RuntimeError("synthetic")):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                self._finish_dungeon(session)
        self.assertFalse(db.has_claimed(1, "dungeon_finish", "run-failure"))
        self.assertEqual(DungeonData.FromString(db.get_dungeon(1, 1001)).finish_times, 0)
        self.assertEqual(self.num(101), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
