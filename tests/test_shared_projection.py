import math
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from proto.net_pb2 import (
    CharacterRecorderData,
    PlayerRecorderData,
    PlayerSceneRecordReq,
    Vector3,
)
from server.shared_projection import ProjectionStore, SharedProjection, _vector
from utils.metrics import metrics


def recorder(position=(1, 2, 3), rotation=(0, 0, 0), char_id=7):
    data = PlayerRecorderData()
    record = data.char_recorder_data_lst.add()
    record.char_id = char_id
    record.pos.CopyFrom(Vector3(x=position[0], y=position[1], z=position[2]))
    record.rot.CopyFrom(Vector3(x=rotation[0], y=rotation[1], z=rotation[2]))
    return data


class SharedProjectionTests(unittest.TestCase):
    def setUp(self):
        metrics.reset()
        self.store = ProjectionStore()

    def tearDown(self):
        metrics.reset()

    def test_recorder_extracts_only_shared_fields(self):
        projection = self.store.update_from_recorder(10, 1, 2, recorder())
        self.assertEqual(projection.player_id, 10)
        self.assertEqual(projection.scene_id, 1)
        self.assertEqual(projection.channel_id, 2)
        self.assertEqual(projection.char_id, 7)
        self.assertEqual(projection.position, (1.0, 2.0, 3.0))
        self.assertEqual(projection.version, 1)

    def test_empty_recorder_does_not_create_projection(self):
        self.assertIsNone(
            self.store.update_from_recorder(10, 1, 2, PlayerRecorderData())
        )
        self.assertEqual(self.store.snapshot(), {})

    def test_non_finite_vectors_are_rejected(self):
        with self.assertRaises(ValueError):
            _vector(SimpleNamespace(x=math.nan, y=0.0, z=0.0))
        self.assertEqual(self.store.snapshot(), {})

    def test_updates_increment_version_and_preserve_action_emoji(self):
        self.store.update_from_recorder(10, 1, 2, recorder())
        self.store.record_action(10, 1, 2, 99)
        self.store.record_emoji(10, 1, 2, 88)
        updated = self.store.update_from_recorder(
            10, 1, 2, recorder(position=(4, 5, 6))
        )
        self.assertEqual(updated.version, 4)
        self.assertEqual(updated.action_id, 0)
        self.assertEqual(updated.emoji_id, 0)

    def test_action_and_emoji_create_projection_when_missing(self):
        action = self.store.record_action(10, 1, 2, 99)
        emoji = self.store.record_emoji(10, 1, 2, 88)
        self.assertEqual(action.action_id, 99)
        self.assertEqual(emoji.emoji_id, 88)
        self.assertEqual(emoji.version, 2)

    def test_move_changes_channel_membership(self):
        self.store.update_from_recorder(10, 1, 2, recorder())
        self.store.update_from_recorder(11, 1, 2, recorder())
        self.store.move(10, 3, 4)
        self.assertEqual(
            {item.player_id for item in self.store.channel_snapshot(1, 2)},
            {11},
        )
        self.assertEqual(
            {item.player_id for item in self.store.channel_snapshot(3, 4)},
            {10},
        )

    def test_remove_clears_projection_and_metrics(self):
        self.store.update_from_recorder(10, 1, 2, recorder())
        removed = self.store.remove(10)
        self.assertEqual(removed.player_id, 10)
        self.assertIsNone(self.store.get(10))
        self.assertEqual(
            metrics.snapshot()["gauges"]["ofps.projection.active"], 0
        )

    def test_concurrent_updates_are_serialized(self):
        def worker(player_id):
            for index in range(100):
                self.store.update_from_recorder(
                    player_id,
                    1,
                    2,
                    recorder(position=(index, 0, 0)),
                )

        threads = [
            threading.Thread(target=worker, args=(player_id,))
            for player_id in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.store.snapshot()), 8)
        self.assertEqual(
            metrics.snapshot()["counters"]["ofps.projection.updates_total"], 800
        )

    def test_restored_projection_expires_without_active_session(self):
        self.store.restore(
            {
                "10": {
                    "player_id": 10,
                    "scene_id": 1,
                    "channel_id": 2,
                    "position": [1.0, 2.0, 3.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "updated_at": 100.0,
                    "restored": True,
                }
            }
        )
        expired = self.store.prune_restored(30.0, now=131.0)
        self.assertEqual([item.player_id for item in expired], [10])
        self.assertIsNone(self.store.get(10))
        self.assertEqual(
            metrics.snapshot()["counters"][
                "ofps.projection.restored_expirations_total"
            ],
            1,
        )

    def test_touch_keeps_reconnected_player_from_expiring(self):
        self.store.restore(
            {
                "10": {
                    "player_id": 10,
                    "scene_id": 1,
                    "channel_id": 2,
                    "position": [1.0, 2.0, 3.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "updated_at": 100.0,
                    "restored": True,
                }
            }
        )
        touched = self.store.touch(10)
        self.assertFalse(touched.restored)
        self.assertEqual(self.store.prune_restored(30.0, now=131.0), ())
        self.assertIsNotNone(self.store.get(10))

    def test_squared_distance_uses_position_only(self):
        first = SharedProjection(1, 1, 1, position=(0.0, 0.0, 0.0))
        second = SharedProjection(2, 1, 1, position=(3.0, 4.0, 0.0))
        self.assertEqual(first.squared_distance(second), 25.0)


class SharedProjectionHandlerIntegrationTests(unittest.TestCase):
    def setUp(self):
        from server import shared_projection

        self.shared_projection = shared_projection
        self.shared_projection.store.clear()
        metrics.reset()

    def tearDown(self):
        self.shared_projection.store.clear()
        metrics.reset()

    def test_player_scene_record_updates_projection(self):
        from handlers.PlayerSceneRecord import Handler

        session = SimpleNamespace(
            player_id=10,
            scene_id=1,
            channel_id=2,
            scene_player=SimpleNamespace(
                team=SimpleNamespace(char1=SimpleNamespace(pos=Vector3(), rot=Vector3()))
            ),
            pos={},
        )
        with patch("handlers.PlayerSceneRecord.up_recorder"), patch(
            "handlers.PlayerSceneRecord.save_session_location"
        ):
            Handler().handle(
                session,
                PlayerSceneRecordReq(data=recorder()).SerializeToString(),
                1,
            )
        projection = self.shared_projection.store.get(10)
        self.assertIsNotNone(projection)
        self.assertEqual(projection.position, (1.0, 2.0, 3.0))


if __name__ == "__main__":
    unittest.main()
