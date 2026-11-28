import tempfile
import time
import unittest
from unittest.mock import patch

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import (
    ActivityBattlePassBuyExpRsp,
    ActivityGiftRewardRsp,
    ActivityQuestRewardRsp,
    ActivityRegularRewardRsp,
    ActivitySignInRsp,
    ActivityTurntableDrawRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
    SupplyBoxInfoRsp,
    SupplyBoxRewardRsp,
)
import handlers.SupplyBoxInfo as supply_info
from server import activities
import utils.db as db
from utils import item_mgr, refresh, res_loader


OK = StatusCode.StatusCode_OK
BAD_REQ = StatusCode.StatusCode_BAD_REQ
CFG_NOT_FOUND = StatusCode.StatusCode_CFG_NOT_FOUND
NOT_FINISHED = StatusCode.StatusCode_NotFinishAllTask
REPEAT = StatusCode.StatusCode_REPEAT_GET_REWARD
NOW = 1_800_000_000
NEXT_DAY = NOW + 86_400
PLAYER = 41


class FakeSession:
    def __init__(self, player_id=PLAYER):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class ActivityRewardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use real Item/ItemDetail behavior; the activity tables below are synthetic
        # so every window, cycle and prerequisite is deterministic.
        res_loader.init()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        db.exit()
        Config.DB_PATH = self.tmp.name + "/player.db"
        Config.IN_MEMORY = False
        db.init()
        db.db.execute(
            "INSERT INTO players(player_id, player_name, create_time) VALUES (?, ?, ?)",
            (PLAYER, "activity-test", NOW - 100_000),
        )
        db.db.execute(
            "INSERT INTO month_card(player_id, over_due_time, reward_days) VALUES (?, ?, ?)",
            (PLAYER, NOW + 30 * 86_400, 0),
        )
        self.start = (NOW - 2 * 86_400) * 1000
        self.end = (NOW + 30 * 86_400) * 1000
        self.instances = {
            aid: (0 if aid == 5 else aid, aid * 100, self.start, self.end)
            for aid in range(1, 8)
        }
        self.config_patch = patch.multiple(
            Config,
            ACTIVITY_VISIBLE_IDS=tuple(self.instances),
            INACTIVE_ACTIVITY_IDS=(),
            ACTIVITY_INSTANCES=self.instances,
            SUPPLY_BOX_REWARDS=((101, 3),),
            TURNTABLE_MAX_DRAW_TIMES=10,
        )
        self.config_patch.start()
        self.global_config = {
            "BattlePass_BuyExp_Currency": ("102:50:1000",),
            "MoonCard_Rveryday_Currency": ("102:90",),
            "MoonCard_MaxRemainingDay": ("180",),
            "SupplyBox_Random_Time": ("10", "30"),
        }
        self.targets = {
            10001: 1,
            10002: 1,
            20001: 1,
            20002: 1,
            20003: 1,
            20004: 1,
            30001: 1,
            40001: 1,
            40002: 1,
            40003: 1,
        }
        self.progress = {key: 0 for key in self.targets}
        self.resources = {
            ("ActivitySign", "activity_sign"): (
                {
                    "i_d": 100,
                    "activity_sign_item": tuple(
                        {
                            "days": day,
                            "activity_sign_reward_item": (
                                {"item_i_d": 101, "item_num": day},
                            ),
                        }
                        for day in range(1, 4)
                    ),
                },
            ),
            ("ActivityQuest", "activity_quest"): (
                {
                    "i_d": 500,
                    "activity_quest_reward_i_d": 501,
                    "activity_quest_achieve_items": (
                        {
                            "days": 1,
                            "achieve_i_d": 10001,
                            "activity_quest_item": (
                                {"item_i_d": 101, "item_num": 2},
                            ),
                        },
                        {
                            "days": 1,
                            "achieve_i_d": 10002,
                            "activity_quest_item": (
                                {"item_i_d": 101, "item_num": 3},
                            ),
                        },
                    ),
                },
            ),
            ("ActivityQuest", "activity_quest_reward"): (
                {
                    "i_d": 501,
                    "activity_quest_reward_item": (
                        {
                            "index": 1,
                            "condition_item_i_d": 102,
                            "condition_item_num": 5,
                            "reward_item_i_d": 101,
                            "reward_item_num": 10,
                        },
                        {
                            "index": 2,
                            "condition_item_i_d": 102,
                            "condition_item_num": 5,
                            "reward_item_i_d": 101,
                            "reward_item_num": 20,
                        },
                    ),
                },
            ),
            ("ActivityRegular", "activity_regular"): (
                {
                    "i_d": 400,
                    "daily_pool_i_d": 401,
                    "daily_refresh_pool_i_d": 402,
                    "random_pool_i_d": 403,
                    "pool_i_d": 404,
                },
            ),
            ("ActivityRegular", "activity_regular_pool"): tuple(
                {
                    "i_d": pool_id,
                    "activity_regular_pool_item": (
                        {
                            "achieve_i_d": achieve_id,
                            "activity_regular_pool_reward_item": (
                                {"item_i_d": 101, "item_num": count},
                            ),
                        },
                    ),
                }
                for pool_id, achieve_id, count in (
                    (401, 20001, 1),
                    (402, 20002, 2),
                    (403, 20003, 3),
                    (404, 20004, 4),
                )
            ),
            ("ActivityGift", "activity_gift"): (
                {
                    "i_d": 200,
                    "activity_gift_item": (
                        {
                            "achieve_i_d": 30001,
                            "a_activity_gift_reward_item": (
                                {"item_i_d": 101, "item_num": 7},
                            ),
                        },
                    ),
                },
            ),
            ("BattlePass", "battle_pass"): (
                {
                    "i_d": 300,
                    "day_quest_i_d": 301,
                    "week_quest_i_d": 302,
                    "season_quest_i_d": 303,
                    "battle_pass_level_ups": (
                        {
                            "level": 1,
                            "battle_pass_reward": (
                                {"item_i_d": 101, "item_num": 11},
                                {"item_i_d": 102, "item_num": 12},
                            ),
                        },
                        {
                            "level": 2,
                            "battle_pass_reward": (
                                {"item_i_d": 101, "item_num": 21},
                                {"item_i_d": 102, "item_num": 22},
                            ),
                        },
                    ),
                },
            ),
            ("BattlePass", "battle_pass_queset"): (
                {
                    "i_d": 301,
                    "battle_pass_queset_item": (
                        {"achieve_i_d": 40001, "exp": 10},
                    ),
                },
                {
                    "i_d": 302,
                    "battle_pass_queset_item": (
                        {"achieve_i_d": 40002, "exp": 20},
                    ),
                },
                {
                    "i_d": 303,
                    "battle_pass_queset_item": (
                        {"achieve_i_d": 40003, "exp": 30},
                    ),
                },
            ),
            ("ActivityTurntable", "activity_turntable"): (
                {
                    "i_d": 600,
                    "turntable_pool_i_d": 601,
                    "cost_item_i_d": 126,
                    "first_one_need_item_num": 6,
                    "one_need_item_num": 1,
                },
            ),
            ("ActivityTurntable", "turntable_pool"): (
                {
                    "i_d": 601,
                    "turntable_pool_item": (
                        {
                            "index": 1,
                            "item_i_d": 101,
                            "item_num": 1,
                            "limit_num": 2,
                            "weight": 9,
                        },
                        {
                            "index": 2,
                            "item_i_d": 102,
                            "item_num": 2,
                            "limit_num": 0,
                            "weight": 1,
                        },
                    ),
                },
            ),
        }
        self.rows_patch = patch.object(activities, "_rows", side_effect=self.resource_rows)
        self.rows_patch.start()
        self.target_patch = patch.object(
            activities.achieve_track, "target_of", side_effect=lambda achieve_id: self.targets.get(achieve_id)
        )
        self.target_patch.start()
        self.progress_patch = patch.object(
            activities.activity_state,
            "condition_progress",
            side_effect=lambda player_id, achieve_id: self.progress.get(achieve_id, 0),
        )
        self.progress_patch.start()
        self.level_patch = patch.object(db, "_bp_level_exps", return_value=(100, 100))
        self.level_patch.start()

    def tearDown(self):
        self.level_patch.stop()
        self.progress_patch.stop()
        self.target_patch.stop()
        self.rows_patch.stop()
        self.config_patch.stop()
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory
        self.tmp.cleanup()

    def resource_rows(self, sheet, table):
        if (sheet, table) == ("GlobalConfig", "config"):
            return tuple({"key": key, "values": values} for key, values in self.global_config.items())
        return self.resources.get((sheet, table), ())

    def restart(self):
        db.exit()
        db.init()

    def set_balance(self, item_id, amount, player_id=PLAYER):
        detail = ItemDetail()
        detail.main_item.item_id = item_id
        detail.main_item.base_item.item_id = item_id
        detail.main_item.base_item.num = amount
        db.set_item_detail(player_id, detail.SerializeToString(), item_id, None)

    def balance(self, item_id, player_id=PLAYER):
        return item_mgr.get_num(player_id, item_id)

    def sign(self, day, now=NOW):
        rsp = ActivitySignInRsp(day=day)
        pack = PackNotice(status=OK)
        status, bitmap = activities.claim_sign_in(PLAYER, 1, day, rsp.rewards, pack, now)
        return status, bitmap, rsp, pack

    def quest(self, param, is_progress=False, now=NOW):
        rsp = ActivityQuestRewardRsp(param=param, is_progress=is_progress)
        pack = PackNotice(status=OK)
        status, claimed = activities.claim_activity_quest(
            PLAYER, 5, param, is_progress, rsp.rewards, pack, now
        )
        return status, claimed, rsp, pack

    def regular(self, pool_type, param, now=NOW):
        rsp = ActivityRegularRewardRsp(pool_type=pool_type, param=param)
        pack = PackNotice(status=OK)
        status = activities.claim_regular_reward(PLAYER, 4, pool_type, param, rsp.rewards, pack, now)
        return status, rsp, pack

    def gift(self, now=NOW):
        rsp = ActivityGiftRewardRsp()
        pack = PackNotice(status=OK)
        status = activities.claim_gift_reward(PLAYER, 2, 30001, rsp.rewards, pack, now)
        return status, rsp, pack

    def buy_exp(self, packet_id, now=NOW):
        rsp = ActivityBattlePassBuyExpRsp(activity_battle_pass_id=3)
        pack = PackNotice(status=OK)
        status, result = activities.buy_battle_pass_exp(PLAYER, 3, packet_id, rsp, pack, now)
        return status, result, rsp, pack

    def turntable(self, packet_id, draw_times=1, now=NOW):
        rsp = ActivityTurntableDrawRsp(activity_id=6)
        pack = PackNotice(status=OK)
        replayed = activities.draw_turntable(PLAYER, 6, draw_times, packet_id, rsp, pack, now)
        return replayed, rsp, pack

    def supply(self, packet_id, now=NOW):
        rsp = SupplyBoxRewardRsp()
        pack = PackNotice(status=OK)
        replayed = activities.claim_supply_box(PLAYER, packet_id, rsp, pack, now)
        return replayed, rsp, pack

    def test_activity_windows_and_unknown_ids_fail_closed(self):
        self.assertEqual(activities.activity_status(1, 1, self.start / 1000 - 1), StatusCode.StatusCode_Activity_Close)
        self.assertEqual(activities.activity_status(1, 1, self.end / 1000 + 1), StatusCode.StatusCode_Activity_Close)
        self.assertEqual(activities.activity_status(999, 1, NOW), CFG_NOT_FOUND)
        self.assertEqual(activities.activity_status(1, 2, NOW), CFG_NOT_FOUND)
        status, bitmap, rsp, _ = self.sign(1, self.start / 1000 - 1)
        self.assertEqual((status, bitmap, len(rsp.rewards)), (StatusCode.StatusCode_Activity_Close, 0, 0))
        self.assertFalse(db.get_claimed(PLAYER, "activity_sign"))

    def test_sign_in_is_sequential_and_survives_restart(self):
        self.assertEqual(self.sign(2)[0], StatusCode.StatusCode_FAIL)
        self.assertEqual(self.sign(1)[0:2], (OK, 1 << 1))
        self.restart()
        status, bitmap, rsp, _ = self.sign(2)
        self.assertEqual((status, bitmap), (OK, (1 << 1) | (1 << 2)))
        self.assertEqual([item.main_item.base_item.num for item in rsp.rewards], [2])
        self.assertEqual(self.balance(101), 3)
        self.assertEqual(self.sign(1)[0], REPEAT)
        self.assertEqual(self.sign(3)[0], OK)
        self.assertEqual(self.balance(101), 6)
        self.assertEqual(self.sign(1, NEXT_DAY)[0], REPEAT)
        self.assertEqual(self.sign(3, NEXT_DAY)[0], REPEAT)

    def test_sign_in_rejects_missing_day_configuration_without_claim(self):
        self.assertEqual(self.sign(9)[0], CFG_NOT_FOUND)
        self.assertFalse(db.get_claimed(PLAYER, "activity_sign"))
        self.assertEqual(self.balance(101), 0)

    def test_quest_batch_grant_failure_rolls_back_items_and_claims(self):
        self.progress.update({10001: 1, 10002: 1})
        original = item_mgr.grant_items

        def fail_after_grant(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic grant failure")

        with patch.object(item_mgr, "grant_items", side_effect=fail_after_grant):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                self.quest(1)
        self.assertEqual(self.balance(101), 0)
        self.assertFalse(db.get_claimed(PLAYER, "activity_quest"))
        status, claimed, rsp, _ = self.quest(1)
        self.assertEqual((status, claimed), (OK, [10001, 10002]))
        self.assertEqual(self.balance(101), 5)
        self.assertEqual(sum(item.main_item.base_item.num for item in rsp.rewards), 5)
        self.assertEqual(self.quest(1)[0], REPEAT)

    def test_quest_progress_requires_previous_tier_and_keeps_condition_item(self):
        self.set_balance(102, 5)
        self.assertEqual(self.quest(2, True)[0], NOT_FINISHED)
        self.assertEqual(self.quest(1, True)[0:2], (OK, []))
        self.assertEqual(self.balance(102), 5)
        self.assertEqual(self.balance(101), 10)
        self.restart()
        self.assertEqual(self.quest(1, True)[0], REPEAT)
        self.assertEqual(self.quest(2, True)[0], OK)
        self.assertEqual(self.balance(102), 5)
        self.assertEqual(self.balance(101), 30)

    def test_quest_progress_rejects_insufficient_condition_items(self):
        self.set_balance(102, 4)
        self.assertEqual(self.quest(1, True)[0], StatusCode.StatusCode_ITEM_NOT_ENOUGH)
        self.assertFalse(db.get_claimed(PLAYER, "activity_quest"))
        self.assertEqual(self.balance(101), 0)

    def test_regular_reward_uses_exact_pool_and_resets_daily(self):
        self.progress[20001] = 1
        self.assertEqual(self.regular(2, 20001)[0], CFG_NOT_FOUND)
        self.assertEqual(self.regular(1, 20001)[0], OK)
        self.assertEqual(self.regular(1, 20001)[0], REPEAT)
        self.assertEqual(self.regular(1, 20001, NEXT_DAY)[0], OK)
        self.assertEqual(self.balance(101), 2)

    def test_regular_reward_requires_completion_and_has_no_fallback_pool(self):
        self.assertEqual(self.regular(1, 20001)[0], NOT_FINISHED)
        self.progress[20003] = 1
        self.assertEqual(self.regular(1, 20003)[0], CFG_NOT_FOUND)
        self.assertFalse(db.get_claimed(PLAYER, "activity_regular"))

    def test_gift_requires_condition_and_is_claimable_once_after_restart(self):
        self.assertEqual(self.gift()[0], NOT_FINISHED)
        self.progress[30001] = 1
        self.assertEqual(self.gift()[0], OK)
        self.restart()
        self.assertEqual(self.gift()[0], StatusCode.StatusCode_ActivityGift_Rewarded)
        self.assertEqual(self.balance(101), 7)

    def test_battle_pass_purchase_requires_configuration_and_funds(self):
        self.set_balance(102, 100)
        self.global_config["BattlePass_BuyExp_Currency"] = ()
        self.assertEqual(self.buy_exp(1)[0], CFG_NOT_FOUND)
        self.assertEqual((self.balance(102), db.bp_get_exp(PLAYER, 3)), (100, (0, 0, 0)))
        self.global_config["BattlePass_BuyExp_Currency"] = ("102:50:1000",)
        self.set_balance(102, 4)
        self.assertEqual(self.buy_exp(2)[0], StatusCode.StatusCode_ITEM_NOT_ENOUGH)
        self.assertEqual(self.balance(102), 4)
        self.assertEqual(db.bp_get_exp(PLAYER, 3), (0, 0, 0))

    def test_battle_pass_purchase_is_atomic_and_idempotent_across_restart(self):
        self.set_balance(102, 100)
        original = db.bp_add_exp

        def fail_after_exp(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic exp failure")

        with patch.object(db, "bp_add_exp", side_effect=fail_after_exp):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                self.buy_exp(7)
        self.assertEqual((self.balance(102), db.bp_get_exp(PLAYER, 3)), (100, (0, 0, 0)))
        status, result, rsp, pack = self.buy_exp(8)
        self.assertEqual((status, result), (OK, (2, 1000, 800)))
        self.assertEqual(self.balance(102), 50)
        saved_rsp = rsp.SerializeToString()
        saved_pack = pack.SerializeToString()
        self.restart()
        status, result, replay_rsp, replay_pack = self.buy_exp(8)
        self.assertEqual((status, result), (OK, (2, 1000, 800)))
        self.assertEqual(replay_rsp.SerializeToString(), saved_rsp)
        self.assertEqual(replay_pack.SerializeToString(), saved_pack)
        self.assertEqual((self.balance(102), db.bp_get_exp(PLAYER, 3)), (50, (2, 1000, 800)))
        self.assertEqual(self.buy_exp(0)[0], BAD_REQ)
        self.assertEqual(self.buy_exp(9)[0], StatusCode.StatusCode_BattlePass_MaxLevel)
        self.assertEqual(self.balance(102), 50)

    def test_battle_pass_quest_periods_and_foreign_quest_rejection(self):
        for achieve_id in (40001, 40002, 40003):
            self.progress[achieve_id] = 1
        self.assertEqual(activities.claim_battle_pass_quest(PLAYER, 3, 20001, NOW)[0], CFG_NOT_FOUND)
        status, result = activities.claim_battle_pass_quest(PLAYER, 3, 40001, NOW)
        self.assertEqual((status, result[0:3]), (OK, (10, 0, 0)))
        self.assertEqual(
            activities.claim_battle_pass_quest(PLAYER, 3, 40001, NOW)[0],
            StatusCode.StatusCode_BattlePass_QuestRewarded,
        )
        self.assertEqual(activities.claim_battle_pass_quest(PLAYER, 3, 40001, NEXT_DAY)[0], OK)
        self.assertEqual(activities.claim_battle_pass_quest(PLAYER, 3, 40002, NOW)[1][0:3], (20, 0, 20))
        self.assertEqual(
            activities.claim_battle_pass_quest(PLAYER, 3, 40003, NOW)[0], OK
        )
        self.assertEqual(
            activities.claim_battle_pass_quest(PLAYER, 3, 40003, NOW)[0],
            StatusCode.StatusCode_BattlePass_QuestRewarded,
        )
        self.restart()
        self.assertEqual(db.bp_get_exp(PLAYER, 3), (0, 70, 70))

    def test_battle_pass_weekly_claim_resets_with_iso_week(self):
        self.progress[40002] = 1
        next_week = NOW + 7 * 86_400
        self.assertEqual(activities.claim_battle_pass_quest(PLAYER, 3, 40002, NOW)[0], OK)
        self.assertEqual(activities.claim_battle_pass_quest(PLAYER, 3, 40002, next_week)[0], OK)
        self.assertEqual(db.bp_get_exp(PLAYER, 3), (0, 40, 40))

    def test_battle_pass_level_rewards_enforce_level_and_entitlement(self):
        self.assertEqual(
            activities.claim_battle_pass_level_reward(PLAYER, 3, 1, True, [], PackNotice(), NOW),
            StatusCode.StatusCode_BattlePass_LevelLimit,
        )
        db.bp_add_exp(PLAYER, 3, 100)
        paid_rsp = ActivityGiftRewardRsp()
        self.assertEqual(
            activities.claim_battle_pass_level_reward(PLAYER, 3, 1, False, paid_rsp.rewards, PackNotice(), NOW),
            StatusCode.StatusCode_BattlePass_Not_Buy,
        )
        db.set_kv(PLAYER, "activity_entitlements", "battle_pass:3", 1)
        self.assertEqual(self.balance(102), 0)
        self.assertEqual(
            activities.claim_battle_pass_level_reward(PLAYER, 3, 1, False, paid_rsp.rewards, PackNotice(), NOW),
            OK,
        )
        self.assertEqual(self.balance(102), 12)
        free_rsp = ActivityGiftRewardRsp()
        self.assertEqual(
            activities.claim_battle_pass_level_reward(PLAYER, 3, 1, True, free_rsp.rewards, PackNotice(), NOW),
            OK,
        )
        self.restart()
        self.assertEqual(
            activities.claim_battle_pass_level_reward(PLAYER, 3, 1, True, [], PackNotice(), NOW),
            StatusCode.StatusCode_BattlePass_LvRewarded,
        )
        self.assertEqual(
            activities.claim_battle_pass_level_reward(PLAYER, 3, 2, False, [], PackNotice(), NOW),
            StatusCode.StatusCode_BattlePass_LevelLimit,
        )

    def test_month_card_missing_config_expiry_and_daily_persistence(self):
        self.global_config["MoonCard_Rveryday_Currency"] = ()
        self.assertEqual(activities.claim_month_card(PLAYER, SupplyBoxRewardRsp().items, PackNotice(), NOW)[0], CFG_NOT_FOUND)
        self.assertEqual(self.balance(102), 0)
        self.assertEqual(db.get_month_card_reward_days(PLAYER), 0)
        self.global_config["MoonCard_Rveryday_Currency"] = (102, 90)
        self.assertEqual(activities.claim_month_card(PLAYER, SupplyBoxRewardRsp().items, PackNotice(), NOW)[0:2], (OK, 1))
        self.assertEqual(
            activities.claim_month_card(PLAYER, SupplyBoxRewardRsp().items, PackNotice(), NOW)[0],
            StatusCode.StatusCode_MOON_CARD_DAYS_LIMIT,
        )
        self.restart()
        self.assertEqual(activities.claim_month_card(PLAYER, SupplyBoxRewardRsp().items, PackNotice(), NEXT_DAY)[0:2], (OK, 2))
        self.assertEqual(self.balance(102), 180)
        db.db.execute("UPDATE month_card SET over_due_time=? WHERE player_id=?", (NOW, PLAYER))
        self.assertEqual(activities.claim_month_card(PLAYER, SupplyBoxRewardRsp().items, PackNotice(), NOW)[0], StatusCode.StatusCode_FAIL)
        self.assertEqual(self.balance(102), 180)

    def test_month_card_grant_failure_rolls_back_reward_day(self):
        original = item_mgr.grant_items

        def fail_after_grant(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic grant failure")

        with patch.object(item_mgr, "grant_items", side_effect=fail_after_grant):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                activities.claim_month_card(PLAYER, SupplyBoxRewardRsp().items, PackNotice(), NOW)
        self.assertEqual((self.balance(102), db.get_month_card_reward_days(PLAYER)), (0, 0))
        self.assertFalse(db.has_claimed(PLAYER, "month_card", str(refresh.day_index(NOW))))

    def test_turntable_weighted_draw_cost_replay_and_restart(self):
        self.set_balance(126, 10)
        with patch.object(activities.random, "choices", side_effect=lambda values, **kwargs: [values[-1]]):
            replayed, rsp, pack = self.turntable(10)
        self.assertFalse(replayed)
        self.assertEqual((rsp.status, list(rsp.reward_indexes)), (OK, [2]))
        self.assertEqual(self.balance(126), 4)
        self.assertEqual(self.balance(102), 2)
        saved_rsp = rsp.SerializeToString()
        saved_pack = pack.SerializeToString()
        self.restart()
        with patch.object(activities.random, "choices", side_effect=AssertionError("must not draw again")):
            replayed, replay_rsp, replay_pack = self.turntable(10)
        self.assertTrue(replayed)
        self.assertEqual(replay_rsp.SerializeToString(), saved_rsp)
        self.assertEqual(replay_pack.SerializeToString(), saved_pack)
        self.assertEqual((self.balance(126), self.balance(102)), (4, 2))
        self.assertEqual(len(db.get_turntable_records(PLAYER, 6)[0]), 1)
        self.assertEqual(self.turntable(10, 2)[1].status, BAD_REQ)

    def test_turntable_rejects_invalid_requests_and_insufficient_funds(self):
        self.set_balance(126, 5)
        self.assertEqual(self.turntable(0)[1].status, BAD_REQ)
        self.assertEqual(self.turntable(1, 11)[1].status, BAD_REQ)
        self.assertEqual(self.turntable(2)[1].status, StatusCode.StatusCode_ITEM_NOT_ENOUGH)
        self.assertEqual(self.balance(126), 5)
        self.assertFalse(db.get_turntable_records(PLAYER, 6)[0])
        self.assertIsNone(db.get_kv(PLAYER, activities._OPERATION_NS, "turntable:6:2"))

    def test_turntable_requires_full_draw_capacity_before_charging(self):
        self.set_balance(126, 10)
        pool = self.resources[("ActivityTurntable", "turntable_pool")][0]
        pool["turntable_pool_item"] = tuple(
            dict(entry, limit_num=1) for entry in pool["turntable_pool_item"]
        )
        with patch.object(activities.random, "choices", side_effect=lambda values, **kwargs: [values[0]]):
            rsp = self.turntable(3, 3)[1]
        self.assertEqual(rsp.status, StatusCode.StatusCode_TURNTABLE_NO_REWARD_REMAIN)
        self.assertEqual(self.balance(126), 10)
        self.assertFalse(db.get_turntable_records(PLAYER, 6)[0])

    def test_turntable_grant_failure_rolls_back_cost_records_and_operation(self):
        self.set_balance(126, 10)
        original = item_mgr.grant_items

        def fail_after_grant(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic grant failure")

        with patch.object(item_mgr, "grant_items", side_effect=fail_after_grant):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                self.turntable(4)
        self.assertEqual(self.balance(126), 10)
        self.assertEqual(self.balance(101), 0)
        self.assertFalse(db.get_turntable_records(PLAYER, 6)[0])
        self.assertIsNone(db.get_kv(PLAYER, activities._OPERATION_NS, "turntable:6:4"))
        self.assertEqual(self.turntable(4)[1].status, OK)
        self.assertEqual(self.balance(126), 4)

    def test_supply_missing_configuration_has_no_side_effects(self):
        with patch.object(Config, "SUPPLY_BOX_REWARDS", ()):
            replayed, rsp, pack = self.supply(1)
        self.assertFalse(replayed)
        self.assertEqual(rsp.status, CFG_NOT_FOUND)
        self.assertFalse(pack.items)
        self.assertIsNone(db.get_kv(PLAYER, "player", "supply_box_next"))
        self.assertEqual(self.balance(101), 0)

    def test_supply_random_cooldown_idempotency_and_restart(self):
        db.set_kv(PLAYER, "player", "supply_box_next", NOW - 1)
        with patch.object(Config, "SUPPLY_BOX_REWARDS", ((9, 101, 1), (1, 102, 2))), \
             patch.object(activities.random, "randint", return_value=10), \
             patch.object(activities.random, "choices", side_effect=lambda values, **kwargs: [values[-1]]):
            replayed, rsp, pack = self.supply(20)
        self.assertFalse(replayed)
        self.assertEqual((rsp.status, rsp.next_reward_time), (OK, NOW + 600))
        self.assertEqual((self.balance(101), self.balance(102)), (0, 2))
        self.assertEqual(self.supply(21)[1].status, StatusCode.StatusCode_FAIL)
        saved_rsp = rsp.SerializeToString()
        saved_pack = pack.SerializeToString()
        self.restart()
        with patch.object(activities.random, "choices", side_effect=AssertionError("must not draw again")):
            replayed, replay_rsp, replay_pack = self.supply(20)
        self.assertTrue(replayed)
        self.assertEqual(replay_rsp.SerializeToString(), saved_rsp)
        self.assertEqual(replay_pack.SerializeToString(), saved_pack)
        self.assertEqual((self.balance(101), self.balance(102)), (0, 2))
        with patch.object(activities.random, "randint", return_value=10):
            self.assertEqual(self.supply(22, NOW + 600)[1].status, OK)
        self.assertEqual((self.balance(101), self.balance(102)), (3, 2))

    def test_supply_grant_failure_rolls_back_reward_cooldown_and_operation(self):
        db.set_kv(PLAYER, "player", "supply_box_next", NOW - 1)
        original = item_mgr.grant_items

        def fail_after_grant(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic grant failure")

        with patch.object(activities.random, "randint", return_value=10), \
             patch.object(item_mgr, "grant_items", side_effect=fail_after_grant):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                self.supply(30)
        self.assertEqual(self.balance(101), 0)
        self.assertEqual(db.get_kv(PLAYER, "player", "supply_box_next"), NOW - 1)
        self.assertIsNone(db.get_kv(PLAYER, activities._OPERATION_NS, "supply-box:0:30"))
        with patch.object(activities.random, "randint", return_value=10):
            self.assertEqual(self.supply(30)[1].status, OK)
        self.assertEqual(self.balance(101), 3)

    def test_supply_info_missing_configuration_does_not_assign_none(self):
        session = FakeSession()
        with patch.object(activities, "supply_next_reward_time", return_value=None):
            supply_info.Handler().handle(session, b"", 1)
        self.assertEqual(session.sent[0][0], MsgId.SupplyBoxInfoRsp)
        self.assertIsInstance(session.sent[0][1], SupplyBoxInfoRsp)
        self.assertEqual(session.sent[0][1].status, CFG_NOT_FOUND)
        self.assertEqual(session.sent[0][1].next_reward_time, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
