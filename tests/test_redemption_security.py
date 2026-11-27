import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import (
    ActivityInviteRewardClaimReq,
    InviteCodeUseReq,
    StatusCode,
    UseRedemptionCodeReq,
)
import handlers.ActivityInviteRewardClaim as invite_claim
import handlers.InviteCodeUse as invite_use
import handlers.UseRedemptionCode as redeem_handler
from server import redemption
import utils.db as db


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class RedemptionSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        Config.DB_PATH = str(Path(self.tmp.name) / "player.db")
        Config.IN_MEMORY = False
        db.exit()
        db.init()
        for player_id in range(1, 6):
            db.conn.execute("INSERT INTO players(player_id,player_name) VALUES(?,?)", (player_id, f"p{player_id}"))
        self.grants = []
        self.grant_patch = patch.object(redemption.db, "grant_rewards", side_effect=self.grant)
        self.grant_mock = self.grant_patch.start()
        self.addCleanup(self.grant_patch.stop)

    def tearDown(self):
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory

    def grant(self, player_id, rewards, rsp_rewards, pack_notice):
        self.grants.append((player_id, tuple(rewards)))
        for item_id, count in rewards:
            if rsp_rewards is None and pack_notice is None:
                continue
            entry = rsp_rewards.add() if rsp_rewards is not None else pack_notice.items.add()
            entry.main_item.item_id = item_id
            entry.main_item.base_item.num = count
            if rsp_rewards is not None and pack_notice is not None:
                pack_notice.items.add().CopyFrom(entry)

    def add_code(self, code="CODE-1234", rewards="101:10,102:2", max_uses=0, expire_time=0):
        db.add_redeem_code(code, rewards, max_uses=max_uses, expire_time=expire_time)

    def test_redemption_is_once_per_player_and_handler_sends_one_notice(self):
        self.add_code()
        session = FakeSession()
        request = UseRedemptionCodeReq(code="CODE-1234").SerializeToString()
        redeem_handler.Handler().handle(session, request, 1)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_OK)
        self.assertEqual(len(session.sent), 2)
        self.assertEqual(session.sent[1][0], MsgId.PackNotice)
        redeem_handler.Handler().handle(session, request, 2)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_REDEMPTION_CODE_USED)
        self.assertEqual(len(self.grants), 1)
        self.assertEqual(db.conn.execute("SELECT used FROM redeem_codes WHERE code='CODE-1234'").fetchone()[0], 1)
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM redeem_code_uses").fetchone()[0], 1)

    def test_global_max_uses_is_atomic_under_concurrency(self):
        self.add_code(max_uses=1)
        barrier = threading.Barrier(2)

        def worker(player_id):
            barrier.wait()
            return redemption.redeem_code(player_id, "CODE-1234", None, None)[0]

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(worker, (1, 2)))
        self.assertEqual(sorted(statuses), [0, 3])
        self.assertEqual(len(self.grants), 1)
        self.assertEqual(db.conn.execute("SELECT used FROM redeem_codes WHERE code='CODE-1234'").fetchone()[0], 1)

    def test_same_player_concurrent_replay_grants_once(self):
        self.add_code()
        barrier = threading.Barrier(4)

        def worker(_):
            barrier.wait()
            return redemption.redeem_code(1, "CODE-1234", None, None)[0]

        with ThreadPoolExecutor(max_workers=4) as executor:
            statuses = list(executor.map(worker, range(4)))
        self.assertEqual(statuses.count(0), 1)
        self.assertEqual(statuses.count(4), 3)
        self.assertEqual(len(self.grants), 1)

    def test_expired_exhausted_missing_and_malformed_codes_do_not_grant(self):
        now = 1000
        self.add_code("EXPIRED-1", expire_time=now)
        self.add_code("MAXED-123", max_uses=1)
        db.conn.execute("UPDATE redeem_codes SET used=1 WHERE code='MAXED-123'")
        cases = (
            ("MISSING-1", 1),
            ("EXPIRED-1", 2),
            ("MAXED-123", 3),
            ("bad", 5),
        )
        for code, expected in cases:
            self.assertEqual(redemption.redeem_code(1, code, None, None, now)[0], expected)
        self.assertEqual(self.grants, [])

    def test_malformed_server_rewards_do_not_consume_code(self):
        for rewards in ("", "101", "101:0", "x:1", "101:-2", "101:1,", "101:1000001"):
            self.add_code("CODE-1234", rewards=rewards)
            self.assertEqual(redemption.redeem_code(1, "CODE-1234", None, None)[0], 6)
            self.assertEqual(db.conn.execute("SELECT used FROM redeem_codes").fetchone()[0], 0)
            self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM redeem_code_uses").fetchone()[0], 0)
        self.assertEqual(self.grants, [])

    def test_grant_failure_rolls_back_counter_and_use_marker(self):
        self.add_code()
        self.grant_mock.side_effect = RuntimeError("synthetic grant failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic grant failure"):
            redemption.redeem_code(1, "CODE-1234", None, None)
        self.assertEqual(db.conn.execute("SELECT used FROM redeem_codes").fetchone()[0], 0)
        self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM redeem_code_uses").fetchone()[0], 0)
        self.grant_mock.side_effect = self.grant
        self.assertEqual(redemption.redeem_code(1, "CODE-1234", None, None)[0], 0)
        self.assertEqual(len(self.grants), 1)

    def test_invite_code_must_be_registered_and_self_invite_is_rejected(self):
        rewards = ((104, 1),)
        self.assertEqual(redemption.use_invite_code(1, "UNKNOWN-1", rewards, None, None)[0], "not_found")
        redemption.register_invite_code("OWNER-123", 1)
        self.assertEqual(redemption.use_invite_code(1, "OWNER-123", rewards, None, None)[0], "self_invite")
        with self.assertRaises(ValueError):
            redemption.register_invite_code("OWNER-123", 2)
        self.assertEqual(self.grants, [])

    def test_invite_code_is_reusable_by_distinct_players_but_bound_once_per_player(self):
        rewards = ((104, 1), (101, 100))
        redemption.register_invite_code("OWNER-123", 1)
        redemption.register_invite_code("OTHER-123", 2)
        self.assertEqual(redemption.use_invite_code(2, "OWNER-123", rewards, None, None)[0], "ok")
        self.assertEqual(redemption.use_invite_code(3, "OWNER-123", rewards, None, None)[0], "ok")
        self.assertEqual(redemption.invite_count(1), 2)
        self.assertEqual(redemption.use_invite_code(2, "OTHER-123", rewards, None, None)[0], "already_filled")
        self.assertEqual(len(self.grants), 2)

    def test_invite_cycles_are_rejected(self):
        rewards = ((104, 1),)
        redemption.register_invite_code("OWNER-123", 1)
        redemption.register_invite_code("OWNER-456", 2)
        redemption.register_invite_code("OWNER-789", 3)
        self.assertEqual(redemption.use_invite_code(2, "OWNER-123", rewards, None, None)[0], "ok")
        self.assertEqual(redemption.use_invite_code(3, "OWNER-456", rewards, None, None)[0], "ok")
        self.assertEqual(redemption.use_invite_code(1, "OWNER-789", rewards, None, None)[0], "cycle")
        self.assertIsNone(db.get_kv(1, "invite", "inviter"))
        self.assertEqual(len(self.grants), 2)

    def test_invite_handler_maps_self_invite_and_closed_activity(self):
        session = FakeSession()
        request = InviteCodeUseReq(code="OWNER-123").SerializeToString()
        with patch.object(invite_use, "_active_invite_activity", return_value=None):
            invite_use.Handler().handle(session, request, 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACTIVITY_INVITE_NOT_OPEN)

        redemption.register_invite_code("OWNER-123", 1)
        with patch.object(invite_use, "_active_invite_activity", return_value=6001), \
             patch.object(invite_use, "_invite_code_rewards", return_value=((104, 1),)):
            invite_use.Handler().handle(session, request, 2)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_INVITE_CODE_IS_SELF)
        self.assertEqual(self.grants, [])

    def test_invite_reward_uses_server_relation_count_and_is_idempotent(self):
        rewards = ((101, 1000),)
        self.assertEqual(
            redemption.claim_invite_reward(1, 6001, 80601001, rewards, 1, 0, None, None),
            "not_completed",
        )
        redemption.register_invite_code("OWNER-123", 1)
        redemption.use_invite_code(2, "OWNER-123", ((104, 1),), None, None)
        self.assertEqual(
            redemption.claim_invite_reward(1, 6001, 80601001, rewards, 1, 0, None, None),
            "ok",
        )
        self.assertEqual(
            redemption.claim_invite_reward(1, 6001, 80601001, rewards, 1, 0, None, None),
            "already_claimed",
        )
        self.assertEqual(len(self.grants), 2)  # invitee reward + one inviter reward

    def test_invite_reward_predecessor_and_grant_rollback(self):
        redemption.register_invite_code("OWNER-123", 1)
        redemption.use_invite_code(2, "OWNER-123", ((104, 1),), None, None)
        redemption.use_invite_code(3, "OWNER-123", ((104, 1),), None, None)
        self.assertEqual(
            redemption.claim_invite_reward(1, 6001, 80601002, ((101, 1000),), 2, 80601001, None, None),
            "not_completed",
        )
        self.grant_mock.side_effect = RuntimeError("synthetic grant failure")
        with self.assertRaises(RuntimeError):
            redemption.claim_invite_reward(1, 6001, 80601001, ((101, 1000),), 1, 0, None, None)
        self.assertFalse(db.has_claimed(1, "activity_invite", "6001:80601001"))
        self.grant_mock.side_effect = self.grant
        self.assertEqual(
            redemption.claim_invite_reward(1, 6001, 80601001, ((101, 1000),), 1, 0, None, None),
            "ok",
        )
        self.assertEqual(
            redemption.claim_invite_reward(1, 6001, 80601002, ((101, 1000),), 2, 80601001, None, None),
            "ok",
        )

    def test_invite_claim_handler_rejects_uncompleted_then_grants_once(self):
        session = FakeSession(1)
        request = ActivityInviteRewardClaimReq(activity_id=6001, condition_id=80601001).SerializeToString()
        with patch.object(invite_claim, "_activity_window", return_value=(0, 0)), \
             patch.object(invite_claim, "_invite_quest_rule", return_value=(((101, 1000),), 1, 0)):
            invite_claim.Handler().handle(session, request, 1)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACTIVITY_INVITE_TASK_NOT_COMPLETED)
            redemption.register_invite_code("OWNER-123", 1)
            redemption.use_invite_code(2, "OWNER-123", ((104, 1),), None, None)
            invite_claim.Handler().handle(session, request, 2)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_OK)
            invite_claim.Handler().handle(session, request, 3)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACTIVITY_INVITE_TASK_CLAIMED)
        self.assertEqual(len(self.grants), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
