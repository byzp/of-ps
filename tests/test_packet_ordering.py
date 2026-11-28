import unittest
from types import SimpleNamespace
from unittest.mock import patch

from network.msg_id import MsgId
from network.packet_factory import PacketFactory


class FakeHandler:
    def __init__(self):
        self.calls = []

    def handle(self, session, data, packet_id):
        self.calls.append((session, data, packet_id))


class FakeExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, fn, *args):
        self.submitted.append((fn, args))
        raise AssertionError("ordered packet must not enter the worker pool")


class MultiplayerPacketOrderingTests(unittest.TestCase):
    def test_position_and_channel_changes_run_on_session_thread(self):
        for msg_id in (MsgId.PlayerSceneRecordReq, MsgId.ChangeSceneChannelReq):
            handler = FakeHandler()
            executor = FakeExecutor()
            session = SimpleNamespace(running=True)
            with patch.object(PacketFactory, "_handlers", {msg_id: handler}), patch.object(
                PacketFactory, "_executor", executor
            ), patch.object(PacketFactory, "_accepting", True):
                accepted = PacketFactory.process_packet(msg_id, b"body", 7, session)
            self.assertIsNot(accepted, False)
            self.assertEqual(handler.calls, [(session, b"body", 7)])
            self.assertEqual(executor.submitted, [])


if __name__ == "__main__":
    unittest.main()
