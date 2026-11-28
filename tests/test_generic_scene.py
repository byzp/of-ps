import unittest
from unittest.mock import patch

from network.msg_id import MsgId
from proto.net_pb2 import CommonParam, GenericSceneAReq, StatusCode
import handlers.GenericSceneA as handler


class FakeSession:
    def __init__(self, player_id=1):
        self.player_id = player_id
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))


class GenericSceneATests(unittest.TestCase):
    def test_preference_channel_round_trip(self):
        session = FakeSession()
        store = {}
        with patch.object(handler.db, 'set_kv', side_effect=lambda player, ns, key, value: store.__setitem__((ns, key), value)), \
             patch.object(handler.db, 'get_kv', side_effect=lambda player, ns, key: store.get((ns, key))):
            handler.Handler().handle(session, GenericSceneAReq(generic_msg_id=9, params=[CommonParam(int_value=1)]).SerializeToString(), 1)
            self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_OK)
            handler.Handler().handle(session, GenericSceneAReq(generic_msg_id=8).SerializeToString(), 2)
        self.assertEqual(session.sent[-1][1].params[0].int_value, 1)

    def test_invalid_preference_value_is_rejected(self):
        session = FakeSession()
        handler.Handler().handle(session, GenericSceneAReq(generic_msg_id=9, params=[CommonParam(int_value=2)]).SerializeToString(), 1)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_BAD_REQ)

    def test_weather_forecast_uses_scene_time(self):
        session = FakeSession()
        with patch.object(handler.weather, 'forecast', return_value=[(8, 1), (9, 2)]):
            handler.Handler().handle(session, GenericSceneAReq(generic_msg_id=4).SerializeToString(), 1)
        rsp = session.sent[-1][1]
        self.assertEqual(rsp.status, StatusCode.StatusCode_OK)
        self.assertEqual([(item.int_value, item.string_value) for item in rsp.params], [(8, '1'), (9, '2')])

    def test_unknown_generic_message_fails_closed(self):
        session = FakeSession()
        handler.Handler().handle(session, GenericSceneAReq(generic_msg_id=999).SerializeToString(), 1)
        self.assertEqual(session.sent[-1][0], MsgId.GenericSceneARsp)
        self.assertEqual(session.sent[-1][1].status, StatusCode.StatusCode_BAD_REQ)


if __name__ == '__main__':
    unittest.main(verbosity=2)
