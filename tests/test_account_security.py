import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
from proto.net_pb2 import (
    AccountNameBindingCancelReq,
    ReportReq,
    SPOperateReq,
    SPOperateType,
    StatusCode,
)
import handlers.AccountNameBindingCancel as binding
import handlers.Report as report
import handlers.SPOperate as sp
import server.payment_security as security
import server.photo_share as photo_share
import utils.db as db


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class AccountSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_path = Config.DB_PATH
        self.old_memory = Config.IN_MEMORY
        Config.DB_PATH = str(Path(self.tmp.name) / "player.db")
        Config.IN_MEMORY = False
        db.exit()
        db.init()
        for player_id in (1, 2, 3):
            db.conn.execute("INSERT INTO players(player_id,player_name,level) VALUES(?,?,?)", (player_id, f"p{player_id}", 10 + player_id))
        with photo_share.lock_sp:
            photo_share.sp_state.clear()
        self.length_patch = patch.object(security, "password_length", return_value=6)
        self.length_patch.start()
        self.addCleanup(self.length_patch.stop)

    def tearDown(self):
        with photo_share.lock_sp:
            photo_share.sp_state.clear()
        db.exit()
        Config.DB_PATH = self.old_path
        Config.IN_MEMORY = self.old_memory

    def operate(self, session, operate_type, password="", old_password=""):
        request = SPOperateReq(
            operate_type=operate_type, password=password, old_password=old_password
        )
        sp.Handler().handle(session, request.SerializeToString(), 1)
        return session.sent[-1][1]

    def test_pbkdf2_hash_has_iterations_and_constant_time_verification(self):
        stored = security.hash_password("123456")
        self.assertTrue(stored.startswith("pbkdf2_sha256$210000$"))
        self.assertNotEqual(stored, "123456")
        self.assertTrue(security.verify_password(stored, "123456"))
        self.assertFalse(security.verify_password(stored, "654321"))
        self.assertFalse(security.verify_password("pbkdf2_sha256$1$00$00", "123456"))

    def test_password_length_and_characters_are_enforced(self):
        self.assertTrue(security.validate_password("123456", 6))
        self.assertFalse(security.validate_password("12345", 6))
        self.assertFalse(security.validate_password("1234567", 6))
        self.assertFalse(security.validate_password("123 56", 6))
        self.assertTrue(security.validate_password("x" * 128, 128))
        self.assertFalse(security.validate_password("x" * 129, 128))
        session = FakeSession()
        self.assertEqual(self.operate(session, SPOperateType.SPOperateType_Open, "12345").status, StatusCode.StatusCode_FAIL)
        state = json.loads(bytes(db.get_kv(1, "secondary_password", "state")).decode())
        self.assertEqual(state["password_hash"], "")
        self.assertEqual(state["failed_attempts"], 1)
        self.assertEqual(self.operate(session, SPOperateType.SPOperateType_Open, "123456").status, StatusCode.StatusCode_OK)

    def test_open_cannot_overwrite_existing_password_and_change_requires_old(self):
        session = FakeSession()
        self.assertEqual(self.operate(session, SPOperateType.SPOperateType_Open, "123456").status, StatusCode.StatusCode_OK)
        self.assertEqual(self.operate(session, SPOperateType.SPOperateType_Open, "654321").status, StatusCode.StatusCode_FAIL)
        self.assertTrue(self.operate(session, SPOperateType.SPOperateType_Check, "123456").sp_check_status)
        self.assertEqual(
            self.operate(session, SPOperateType.SPOperateType_Change, "abcdef", "000000").status,
            StatusCode.StatusCode_FAIL,
        )
        self.assertEqual(
            self.operate(session, SPOperateType.SPOperateType_Change, "abcdef", "123456").status,
            StatusCode.StatusCode_OK,
        )
        self.assertFalse(self.operate(session, SPOperateType.SPOperateType_Check, "123456").sp_check_status)
        self.assertTrue(self.operate(session, SPOperateType.SPOperateType_Check, "abcdef").sp_check_status)

    def test_close_requires_password_and_clears_state(self):
        session = FakeSession()
        self.assertEqual(self.operate(session, SPOperateType.SPOperateType_Close, "123456").status, StatusCode.StatusCode_FAIL)
        self.operate(session, SPOperateType.SPOperateType_Open, "123456")
        self.assertEqual(self.operate(session, SPOperateType.SPOperateType_Close, "000000").status, StatusCode.StatusCode_FAIL)
        response = self.operate(session, SPOperateType.SPOperateType_Close, "123456")
        self.assertEqual(response.status, StatusCode.StatusCode_OK)
        self.assertFalse(response.sp_open_status)
        state = json.loads(bytes(db.get_kv(1, "secondary_password", "state")).decode())
        self.assertEqual(state["password_hash"], "")
        self.assertFalse(state["open"])

    def test_lockout_is_persistent_and_correct_password_waits_for_expiry(self):
        for _ in range(5):
            ok, reason, state, _ = security.secondary_password_operation(1, "check", "000000", "", now=1000)
            self.assertFalse(ok)
        # Set a known password without consuming another check attempt.
        ok, _, _, _ = security.secondary_password_operation(1, "open", "123456", "", now=1000)
        self.assertTrue(ok)
        for _ in range(5):
            security.secondary_password_operation(1, "check", "000000", "", now=1000)
        state = security.load_secondary_state(1)
        self.assertEqual(state["failed_attempts"], 5)
        self.assertEqual(state["locked_until"], 1900)

        db.exit()
        db.init()
        with photo_share.lock_sp:
            photo_share.sp_state.clear()
        ok, reason, _, _ = security.secondary_password_operation(1, "check", "123456", "", now=1899)
        self.assertFalse(ok)
        self.assertEqual(reason, "locked")
        ok, reason, state, verified = security.secondary_password_operation(1, "check", "123456", "", now=1900)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertEqual(state["failed_attempts"], 0)
        self.assertTrue(verified)

    def test_successful_check_resets_failure_counter(self):
        security.secondary_password_operation(1, "open", "123456", "", now=1000)
        for _ in range(4):
            security.secondary_password_operation(1, "check", "000000", "", now=1000)
        ok, _, state, _ = security.secondary_password_operation(1, "check", "123456", "", now=1000)
        self.assertTrue(ok)
        self.assertEqual(state["failed_attempts"], 0)

    def test_legacy_plaintext_snapshot_is_migrated_after_successful_check(self):
        with photo_share.lock_sp:
            photo_share.sp_state[1] = {"password": "123456", "open": True}
        ok, _, state, _ = security.secondary_password_operation(1, "check", "123456", "", now=1000)
        self.assertTrue(ok)
        self.assertTrue(state["password_hash"].startswith("pbkdf2_sha256$210000$"))
        self.assertNotIn("123456", state["password_hash"])
        self.assertTrue(security.verify_password(state["password_hash"], "123456"))

    def test_corrupt_security_state_fails_closed(self):
        db.set_kv(1, "secondary_password", "state", b"not-json")
        session = FakeSession()
        response = self.operate(session, SPOperateType.SPOperateType_Check, "123456")
        self.assertEqual(response.status, StatusCode.StatusCode_SYS_ERR)
        self.assertFalse(response.sp_check_status)

    def test_binding_cancel_requires_binding_and_fresh_session_password_check(self):
        session = FakeSession()
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACCOUNT_NAME_NOT_BIND)

        db.set_kv(1, "account_name_binding", "name", b"bound-name")
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 2)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACCOUNT_NAME_BIND_FAIL)

        self.operate(session, SPOperateType.SPOperateType_Open, "123456")
        other = FakeSession()
        self.operate(other, SPOperateType.SPOperateType_Check, "123456")
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 3)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACCOUNT_NAME_BIND_FAIL)

        self.assertTrue(self.operate(session, SPOperateType.SPOperateType_Check, "123456").sp_check_status)
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 4)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_OK)
        self.assertIsNone(db.get_kv(1, "account_name_binding", "name"))
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 5)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACCOUNT_NAME_NOT_BIND)

    def test_password_change_invalidates_previous_binding_verification(self):
        db.set_kv(1, "account_name_binding", "name", b"bound-name")
        session = FakeSession()
        self.operate(session, SPOperateType.SPOperateType_Open, "123456")
        self.operate(session, SPOperateType.SPOperateType_Change, "abcdef", "123456")
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACCOUNT_NAME_BIND_FAIL)
        self.operate(session, SPOperateType.SPOperateType_Check, "abcdef")
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 2)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_OK)

        db.set_kv(1, "account_name_binding", "name", b"bound-name")
        self.operate(session, SPOperateType.SPOperateType_Check, "abcdef")
        self.operate(session, SPOperateType.SPOperateType_Change, "123456", "abcdef")
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 3)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACCOUNT_NAME_BIND_FAIL)

    def test_expired_binding_verification_is_rejected(self):
        db.set_kv(1, "account_name_binding", "name", b"bound-name")
        session = FakeSession()
        self.operate(session, SPOperateType.SPOperateType_Open, "123456")
        state = security.load_secondary_state(1)
        session._ofps_sp_verified = (1, time.monotonic() - 301, security.state_fingerprint(state))
        binding.Handler().handle(session, AccountNameBindingCancelReq().SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ACCOUNT_NAME_BIND_FAIL)

    def test_report_rejects_self_oversize_and_uses_server_identity(self):
        session = FakeSession()
        report.Handler().handle(session, ReportReq(reported_player_id=1).SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_BAD_REQ)
        report.Handler().handle(session, ReportReq(reported_player_id=2, reason="x" * 513).SerializeToString(), 2)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_ILLEGAL_LEN)

        request = ReportReq(
            reported_player_id=2, reported_role_name="forged\nname", reported_role_level=999,
            reason="bad\nbehavior", chat_content="content",
        )
        with self.assertLogs(report.logger, level="INFO") as logs:
            report.Handler().handle(session, request.SerializeToString(), 3)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_OK)
        output = "\n".join(logs.output)
        self.assertIn("'p2'", output)
        self.assertIn("reported_role_level=12", output)
        self.assertNotIn("forged", output)
        self.assertNotIn("999", output)
        self.assertIn("bad\\nbehavior", output)

        report.Handler().handle(session, request.SerializeToString(), 4)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_REPORT_TIME_LIMIT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
