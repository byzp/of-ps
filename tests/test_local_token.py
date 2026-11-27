import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import Config
from handlers.VerifyLoginToken import Handler
from proto.net_pb2 import StatusCode, VerifyLoginTokenReq


class FakeSession:
    def __init__(self):
        self.verified = False
        self.player_id = 0
        self.sent = []

    def send(self, msg_id, message, packet_id):
        self.sent.append((msg_id, message, packet_id))


class LocalTokenTests(unittest.TestCase):
    def handle(self, uid, token):
        session = FakeSession()
        request = VerifyLoginTokenReq(
            sdk_uid=str(uid),
            login_token=token,
            account_type=1,
            device_uuid="test-device",
        )
        with patch("handlers.VerifyLoginToken.db.get_user_id", return_value=uid), \
             patch("handlers.VerifyLoginToken.db.get_player_id", return_value=1000000 + uid), \
             patch("handlers.VerifyLoginToken.db.verify_sdk_user_info", return_value=False), \
             patch("handlers.VerifyLoginToken.lock_session"), \
             patch("handlers.VerifyLoginToken.session_list", []):
            Handler().handle(session, request.SerializeToString(), 1)
        return session

    def test_local_token_is_rejected_by_default(self):
        with patch.object(Config, "ALLOW_LOCAL_TOKEN", False), patch.object(
            Config, "LOCAL_TOKEN_UIDS", (1000000,)
        ):
            session = self.handle(1000000, "local-session")
        self.assertFalse(session.verified)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_FAIL)

    def test_allowlisted_uid_can_use_local_token_when_enabled(self):
        with patch.object(Config, "ALLOW_LOCAL_TOKEN", True), patch.object(
            Config, "LOCAL_TOKEN_UIDS", (1000000,)
        ):
            session = self.handle(1000000, "local-session")
        self.assertTrue(session.verified)
        self.assertEqual(session.player_id, 2000000)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_OK)

    def test_non_allowlisted_uid_is_rejected(self):
        with patch.object(Config, "ALLOW_LOCAL_TOKEN", True), patch.object(
            Config, "LOCAL_TOKEN_UIDS", (1000000,)
        ):
            session = self.handle(1000001, "local-session")
        self.assertFalse(session.verified)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_FAIL)

    def test_wrong_token_is_rejected(self):
        with patch.object(Config, "ALLOW_LOCAL_TOKEN", True), patch.object(
            Config, "LOCAL_TOKEN_UIDS", (1000000,)
        ):
            session = self.handle(1000000, "wrong-token")
        self.assertFalse(session.verified)
        self.assertEqual(session.sent[0][1].status, StatusCode.StatusCode_FAIL)


if __name__ == "__main__":
    unittest.main()
