import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from config import Config
from handlers.PlayerLogin import Handler
from proto.net_pb2 import PlayerLoginReq


class FakeSession:
    def __init__(self):
        self.player_id = 1000000
        self.player_name = ""
        self.scene_id = 1
        self.channel_id = 1
        self.logged_in = False
        self.sent = []

    def send(self, msg_id, message, packet_id):
        self.sent.append((msg_id, message, packet_id))


class PlayerLoginStateTests(unittest.TestCase):
    def test_successful_login_marks_session_active_and_name(self):
        session = FakeSession()
        request = PlayerLoginReq(is_reconnect=False)
        with patch.object(Config, "SKIP_QUESTS", False), patch(
            "handlers.PlayerLogin.achieve_track.batch", return_value=nullcontext()
        ), patch("handlers.PlayerLogin.achieve_track.daily_login"), patch(
            "handlers.PlayerLogin.achieve_track.captain_level"
        ), patch(
            "handlers.PlayerLogin.db.get_players_info",
            side_effect=[[1], ("region", 0, 0, "tester", "log-token")],
        ), patch(
            "handlers.PlayerLogin.db.get_analysis_account_id", return_value="analysis"
        ), patch("handlers.PlayerLogin.db.get_kv", return_value=0), patch(
            "handlers.PlayerLogin.scene_data.restore_session_location", return_value=False
        ), patch("handlers.PlayerLogin.scene_data.get_scene_id", return_value=1), patch(
            "handlers.PlayerLogin.scene_data.get_channel_id", return_value=1
        ):
            Handler().handle(session, request.SerializeToString(), 1)

        self.assertTrue(session.logged_in)
        self.assertEqual(session.player_name, "tester")
        self.assertEqual(session.sent[0][1].player_name, "tester")


if __name__ == "__main__":
    unittest.main()
