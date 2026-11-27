import contextlib
import unittest
from unittest.mock import patch

from proto.net_pb2 import MPPlayRoomRewardInfoReq, StatusCode
from server import mp_room_rewards
import handlers.MPPlayRoomRewardInfo as handler
import utils.db as db


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class MPRoomRewardTests(unittest.TestCase):
    def setUp(self):
        self.store = {}

    def patch_db(self):
        return [
            patch.object(db, 'get_kv', side_effect=lambda player, ns, key: self.store.get((ns, key))),
            patch.object(db, 'set_kv', side_effect=lambda player, ns, key, value: self.store.__setitem__((ns, key), value)),
            patch.object(db, 'transaction', side_effect=contextlib.nullcontext),
        ]

    def test_consume_is_persistent_and_capped(self):
        for item in self.patch_db():
            item.start()
            self.addCleanup(item.stop)
        self.assertEqual(mp_room_rewards.remaining(1, 'score', 'day'), 10)
        self.assertTrue(mp_room_rewards.consume(1, 'score', 'day', 4))
        self.assertEqual(mp_room_rewards.remaining(1, 'score', 'day'), 6)
        self.assertFalse(mp_room_rewards.consume(1, 'score', 'day', 7))
        self.assertEqual(mp_room_rewards.remaining(1, 'score', 'day'), 6)

    def test_new_period_resets_remaining(self):
        for item in self.patch_db():
            item.start()
            self.addCleanup(item.stop)
        with patch.object(mp_room_rewards, 'period_key', return_value='day-a'):
            mp_room_rewards.consume(1, 'extra_bonus', 'day', 10)
        with patch.object(mp_room_rewards, 'period_key', return_value='day-b'):
            self.assertEqual(mp_room_rewards.remaining(1, 'extra_bonus', 'day'), 10)

    def test_handler_uses_persisted_values(self):
        session = FakeSession()
        with patch.object(handler.mp_room_rewards, 'remaining', side_effect=[3, 21, 2, 20, 1, 19]):
            handler.Handler().handle(session, MPPlayRoomRewardInfoReq().SerializeToString(), 1)
        rsp = session.sent[0][1]
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual((rsp.score_day_remain, rsp.score_week_remain), (3, 21))
        self.assertEqual((rsp.extra_bonus_day_remain, rsp.extra_bonus_week_remain), (2, 20))
        self.assertEqual((rsp.extra_mag_day_remain, rsp.extra_mag_week_remain), (1, 19))


if __name__ == '__main__':
    unittest.main(verbosity=2)
