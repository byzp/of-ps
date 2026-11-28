import unittest

from network import remote_link
from network.msg_id import MsgId
from proto.net_pb2 import (
    CharacterRecorderData,
    LinkMessage,
    PlayerInfo,
    PlayerRecorderData,
    PlayerSceneSyncDataNotice,
    SceneActionType,
    ServerSceneSyncDataNotice,
    Vector3,
)
from server import scene_data, shared_projection
from server.scene_data import _session_list, lock_session
from utils.metrics import metrics


def recorder(x, y, z=0):
    data = PlayerRecorderData()
    record = data.char_recorder_data_lst.add()
    record.char_id = 1
    record.pos.CopyFrom(Vector3(x=x, y=y, z=z))
    return data


class RemotePlayerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.old_sessions = list(_session_list)
        self.old_server_ids = dict(remote_link._server_ids)
        self.old_conv_to_addr = dict(remote_link._conv_to_addr)
        _session_list.clear()
        remote_link._server_ids.clear()
        remote_link._conv_to_addr.clear()
        scene_data._scene.clear()
        scene_data._scene_snapshot.clear()
        scene_data._scene_action.clear()
        shared_projection.store.clear()
        metrics.reset()

    def tearDown(self):
        _session_list[:] = self.old_sessions
        remote_link._server_ids.clear()
        remote_link._server_ids.update(self.old_server_ids)
        remote_link._conv_to_addr.clear()
        remote_link._conv_to_addr.update(self.old_conv_to_addr)
        scene_data._scene.clear()
        scene_data._scene_snapshot.clear()
        scene_data._scene_action.clear()
        shared_projection.store.clear()
        metrics.reset()

    def add_remote(self):
        remote = remote_link.RemoteSession(
            "peer", PlayerInfo(player_id=1, player_name="remote", scene_id=1, channel_id=1)
        )
        with lock_session:
            _session_list.append(remote)
        return remote

    def test_remote_ids_use_reserved_high_range(self):
        player_id = remote_link._trans_id("peer", 1)
        self.assertGreaterEqual(player_id, remote_link.REMOTE_PLAYER_ID_BASE)
        self.assertTrue(remote_link.is_remote_player_id(player_id))
        self.assertFalse(remote_link.is_remote_player_id(10001))

    def test_connection_does_not_prepopulate_legacy_remote_id_base(self):
        link = remote_link._Link(("127.0.0.1", 1))
        with remote_link._lock:
            remote_link._establish_locked(link, 123, "peer", 100.0, True)
        self.assertNotIn("peer", remote_link._server_ids)
        self.assertGreaterEqual(
            remote_link._trans_id("peer", 1), remote_link.REMOTE_PLAYER_ID_BASE
        )

    def test_link_message_pack_roundtrip_uses_bytes(self):
        message = LinkMessage(id="roundtrip", type=LinkMessage.HEARTBEAT)
        unpacked = remote_link._unpack(remote_link._pack(message))
        self.assertEqual(unpacked.id, "roundtrip")
        self.assertEqual(unpacked.type, LinkMessage.HEARTBEAT)

    def test_remote_position_updates_projection_and_snapshot(self):
        remote = self.add_remote()
        notice = PlayerSceneSyncDataNotice()
        item = notice.data.add(player_id=1)
        item.data.add().CopyFrom(recorder(10, 20))
        remote_link._handle_data(
            "peer",
            [1, 1],
            MsgId.PlayerSceneSyncDataNotice,
            notice.SerializeToString(),
        )
        projection = shared_projection.store.get(remote.player_id)
        self.assertIsNotNone(projection)
        self.assertEqual(projection.position, (10.0, 20.0, 0.0))
        self.assertIn(remote.player_id, scene_data.get_scene_snapshot(1, 1))

    def test_remote_enter_moves_projection_and_clears_old_channel(self):
        remote = self.add_remote()
        shared_projection.store.update_from_recorder(
            remote.player_id, 1, 1, recorder(1, 2)
        )
        scene_data.up_recorder(1, 1, remote.player_id, recorder(1, 2))
        notice = ServerSceneSyncDataNotice()
        item = notice.data.add(player_id=1)
        action = item.server_data.add(action_type=SceneActionType.SceneActionType_ENTER)
        action.player.player_id = 1
        remote_link._handle_data(
            "peer",
            [2, 2],
            MsgId.ServerSceneSyncDataNotice,
            notice.SerializeToString(),
        )
        self.assertEqual((remote.scene_id, remote.channel_id), (2, 2))
        self.assertNotIn(remote.player_id, scene_data.get_scene_snapshot(1, 1))
        projection = shared_projection.store.get(remote.player_id)
        self.assertEqual((projection.scene_id, projection.channel_id), (2, 2))

    def test_remote_leave_removes_session_projection_and_pending_recorder(self):
        remote = self.add_remote()
        shared_projection.store.update_from_recorder(
            remote.player_id, 1, 1, recorder(1, 2)
        )
        scene_data.up_recorder(1, 1, remote.player_id, recorder(1, 2))
        notice = ServerSceneSyncDataNotice()
        item = notice.data.add(player_id=1)
        item.server_data.add(action_type=SceneActionType.SceneActionType_LEAVE)
        remote_link._handle_data(
            "peer",
            [1, 1],
            MsgId.ServerSceneSyncDataNotice,
            notice.SerializeToString(),
        )
        self.assertNotIn(remote, _session_list)
        self.assertFalse(remote.running)
        self.assertIsNone(shared_projection.store.get(remote.player_id))
        self.assertNotIn(remote.player_id, scene_data.get_scene_snapshot(1, 1))
        self.assertNotIn(remote.player_id, scene_data.get_recorder(1, 1))

    def test_disconnect_cleans_all_remote_players_from_origin(self):
        first = self.add_remote()
        second = remote_link.RemoteSession(
            "peer", PlayerInfo(player_id=2, player_name="remote-2", scene_id=1, channel_id=1)
        )
        with lock_session:
            _session_list.append(second)
        for remote in (first, second):
            shared_projection.store.update_from_recorder(
                remote.player_id, 1, 1, recorder(1, 2)
            )
            scene_data.up_recorder(1, 1, remote.player_id, recorder(1, 2))
        remote_link._drop_remote_sessions("peer")
        self.assertEqual(_session_list, [])
        self.assertEqual(shared_projection.store.snapshot(), {})
        self.assertEqual(scene_data.get_scene_snapshot(1, 1), {})


if __name__ == "__main__":
    unittest.main()
