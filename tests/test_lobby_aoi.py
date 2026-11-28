import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import Config
from proto.net_pb2 import CharacterRecorderData, PlayerRecorderData, Vector3
from server import notice_sync, shared_projection
from server.scene_data import _rec_list, _scene, _scene_snapshot, _session_list
from utils.metrics import metrics


def recorder(x, y=0, z=0):
    data = PlayerRecorderData()
    record = data.char_recorder_data_lst.add()
    record.char_id = 1
    record.pos.CopyFrom(Vector3(x=x, y=y, z=z))
    return data


class FakeSession:
    def __init__(self, player_id, scene_id=1, channel_id=1):
        self.player_id = player_id
        self.scene_id = scene_id
        self.channel_id = channel_id
        self.running = True
        self.logged_in = True
        self.sent = []

    def send(self, msg_id, message, packet_id):
        self.sent.append((msg_id, message, packet_id))


class LobbyAoiTests(unittest.TestCase):
    def setUp(self):
        self.old_sessions = list(_session_list)
        self.old_scene = {
            (scene_id, channel_id): dict(players)
            for scene_id, channels in _scene.items()
            for channel_id, players in channels.items()
        }
        self.old_rec_list = list(_rec_list)
        _session_list.clear()
        _scene.clear()
        _scene_snapshot.clear()
        _rec_list.clear()
        shared_projection.store.clear()
        notice_sync._last_global_position_sync.clear()
        metrics.reset()

    def tearDown(self):
        _session_list[:] = self.old_sessions
        _scene.clear()
        _scene_snapshot.clear()
        for (scene_id, channel_id), players in self.old_scene.items():
            _scene[scene_id][channel_id].update(players)
        _rec_list[:] = self.old_rec_list
        shared_projection.store.clear()
        notice_sync._last_global_position_sync.clear()
        metrics.reset()

    def queue_positions(self, positions):
        _scene[1][1].clear()
        _scene_snapshot[1][1].clear()
        for player_id, (x, y, z) in positions.items():
            value = recorder(x, y, z)
            _scene[1][1][player_id] = value
            _scene_snapshot[1][1][player_id] = value
        _rec_list[:] = [(1, 1)]

    def populate(self, positions):
        sessions = []
        for player_id, (x, y, z) in positions.items():
            session = FakeSession(player_id)
            sessions.append(session)
            _session_list.append(session)
            shared_projection.store.update(
                shared_projection.SharedProjection(
                    player_id=player_id,
                    scene_id=1,
                    channel_id=1,
                    position=(float(x), float(y), float(z)),
                )
            )
        self.queue_positions(positions)
        return sessions

    def test_global_due_sends_all_players_to_every_session(self):
        sessions = self.populate({1: (0, 0, 0), 2: (5, 0, 0), 3: (50, 0, 0)})
        with patch.object(notice_sync, "rsend"), patch.object(
            Config, "SCENE_AOI_RADIUS", 10.0
        ), patch.object(Config, "SCENE_GLOBAL_SYNC_INTERVAL", 0.5):
            notice_sync._broadcast_position_updates(100.0)
        for session in sessions:
            self.assertEqual(len(session.sent), 1)
            message = session.sent[0][1]
            self.assertEqual(
                {item.player_id for item in message.data}, {1, 2, 3}
            )
        self.assertEqual(
            metrics.snapshot()["counters"]["ofps.notice.position_global_sends"],
            3,
        )

    def test_global_snapshot_includes_players_without_new_updates(self):
        sessions = self.populate({1: (0, 0, 0), 2: (5, 0, 0), 3: (50, 0, 0)})
        _scene[1][1].clear()
        _scene[1][1][1] = recorder(0, 0, 0)
        with patch.object(notice_sync, "rsend"), patch.object(
            Config, "SCENE_AOI_RADIUS", 10.0
        ), patch.object(Config, "SCENE_GLOBAL_SYNC_INTERVAL", 0.5):
            notice_sync._broadcast_position_updates(100.0)
        for session in sessions:
            self.assertEqual(
                {item.player_id for item in session.sent[0][1].data}, {1, 2, 3}
            )

    def test_aoi_tick_filters_distant_players_but_keeps_self(self):
        sessions = self.populate({1: (0, 0, 0), 2: (5, 0, 0), 3: (50, 0, 0)})
        with patch.object(notice_sync, "rsend"), patch.object(
            Config, "SCENE_AOI_RADIUS", 10.0
        ), patch.object(Config, "SCENE_GLOBAL_SYNC_INTERVAL", 0.5):
            notice_sync._broadcast_position_updates(100.0)
            for session in sessions:
                session.sent.clear()
            self.queue_positions({1: (0, 0, 0), 2: (5, 0, 0), 3: (50, 0, 0)})
            notice_sync._broadcast_position_updates(100.1)
        by_player = {session.player_id: session for session in sessions}
        self.assertEqual(
            {item.player_id for item in by_player[1].sent[0][1].data}, {1, 2}
        )
        self.assertEqual(
            {item.player_id for item in by_player[3].sent[0][1].data}, {3}
        )
        self.assertEqual(
            metrics.snapshot()["counters"]["ofps.notice.position_aoi_sends"],
            3,
        )

    def test_missing_projection_falls_back_to_global_snapshot(self):
        sessions = self.populate({1: (0, 0, 0), 2: (5, 0, 0), 3: (50, 0, 0)})
        shared_projection.store.remove(3)
        with patch.object(notice_sync, "rsend"), patch.object(
            Config, "SCENE_AOI_RADIUS", 10.0
        ), patch.object(Config, "SCENE_GLOBAL_SYNC_INTERVAL", 0.5):
            notice_sync._broadcast_position_updates(100.0)
            for session in sessions:
                session.sent.clear()
            self.queue_positions({1: (0, 0, 0), 2: (5, 0, 0), 3: (50, 0, 0)})
            notice_sync._broadcast_position_updates(100.1)
        by_player = {session.player_id: session for session in sessions}
        self.assertEqual(
            {item.player_id for item in by_player[3].sent[0][1].data}, {1, 2, 3}
        )

    def test_zero_radius_preserves_full_broadcast(self):
        sessions = self.populate({1: (0, 0, 0), 2: (50, 0, 0)})
        with patch.object(notice_sync, "rsend"), patch.object(
            Config, "SCENE_AOI_RADIUS", 0.0
        ), patch.object(Config, "SCENE_GLOBAL_SYNC_INTERVAL", 0.5):
            notice_sync._broadcast_position_updates(100.0)
            for session in sessions:
                session.sent.clear()
            self.queue_positions({1: (0, 0, 0), 2: (50, 0, 0)})
            notice_sync._broadcast_position_updates(100.1)
        for session in sessions:
            self.assertEqual(len(session.sent), 1)
            self.assertEqual(
                {item.player_id for item in session.sent[0][1].data}, {1, 2}
            )

    def test_remote_players_remain_visible(self):
        sessions = self.populate({1: (0, 0, 0), 2: (5, 0, 0)})
        _scene[1][1][2000000] = recorder(50, 0, 0)
        _scene_snapshot[1][1][2000000] = recorder(50, 0, 0)
        with patch.object(notice_sync, "rsend"), patch.object(
            Config, "SCENE_AOI_RADIUS", 10.0
        ), patch.object(Config, "SCENE_GLOBAL_SYNC_INTERVAL", 0.5):
            notice_sync._broadcast_position_updates(100.0)
            for session in sessions:
                session.sent.clear()
            self.queue_positions({1: (0, 0, 0), 2: (5, 0, 0)})
            _scene[1][1][2000000] = recorder(50, 0, 0)
            _scene_snapshot[1][1][2000000] = recorder(50, 0, 0)
            notice_sync._broadcast_position_updates(100.1)
        for session in sessions:
            self.assertIn(
                2000000,
                {item.player_id for item in session.sent[0][1].data},
            )


if __name__ == "__main__":
    unittest.main()
