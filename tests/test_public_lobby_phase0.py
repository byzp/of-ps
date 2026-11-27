import socket
import struct
import threading
import unittest
from unittest.mock import patch

from config import Config
from http_server.handlers.dispatch_handler import DispatchHandler
import main as main_module
from network.game_session import GameSession
from network.msg_id import MsgId
from network.packet_factory import PacketFactory
from proto.net_pb2 import PacketHead, PlayerPingReq
from handlers.PlayerPing import Handler as PlayerPingHandler
from server import notice_sync
from utils.metrics import MetricsRegistry, metrics


def _frame(msg_id, body=b"", packet_id=1):
    head = PacketHead(msg_id=msg_id, packet_id=packet_id, body_len=len(body))
    payload = head.SerializeToString()
    return struct.pack(">H", len(payload)) + payload + body


class FakeSocket:
    def __init__(self):
        self.sent = bytearray()
        self.send_entered = threading.Event()
        self.closed = threading.Event()

    def setsockopt(self, *args):
        pass

    def settimeout(self, timeout):
        pass

    def shutdown(self, how):
        self.closed.set()

    def close(self):
        self.closed.set()

    def sendall(self, data):
        self.send_entered.set()
        self.sent.extend(data)


class ConfigValidationTests(unittest.TestCase):
    def test_default_network_config_is_valid(self):
        Config.validate()

    def test_invalid_port_is_rejected(self):
        with patch.object(Config, "HTTP_PORT", 0):
            with self.assertRaisesRegex(ValueError, "HTTP_PORT"):
                Config.validate()

    def test_dispatch_listener_port_mismatch_is_rejected(self):
        with patch.object(Config, "GAME_SERVER_GADGET_PORT", 25566):
            with self.assertRaisesRegex(ValueError, "must match"):
                Config.validate()

    def test_dispatch_advertises_actual_listener_port(self):
        region = DispatchHandler.region_info()
        self.assertEqual(region["gate_tcp_port"], Config.GAME_SERVER_PORT)
        self.assertEqual(region["client_log_tcp_port"], Config.GAME_SERVER_PORT)

    def test_main_validates_before_starting_workers(self):
        with patch.object(Config, "validate", side_effect=ValueError("bad config")), \
             patch.object(main_module.cmd, "start") as start:
            with self.assertRaisesRegex(ValueError, "bad config"):
                main_module.main()
        start.assert_not_called()


class MetricsRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = MetricsRegistry()

    def test_counters_gauges_and_timers_are_snapshotted(self):
        self.registry.inc("requests", 2)
        self.registry.inc("requests", 3)
        self.registry.set("active", 4)
        self.registry.observe("latency", 0.01)
        self.registry.observe("latency", 0.03)

        snapshot = self.registry.snapshot()
        self.assertEqual(snapshot["counters"]["requests"], 5)
        self.assertEqual(snapshot["gauges"]["active"], 4)
        self.assertEqual(snapshot["timers"]["latency"]["count"], 2)
        self.assertAlmostEqual(snapshot["timers"]["latency"]["total_seconds"], 0.04)
        self.assertAlmostEqual(snapshot["timers"]["latency"]["max_seconds"], 0.03)
        self.assertAlmostEqual(snapshot["timers"]["latency"]["avg_seconds"], 0.02)

    def test_concurrent_increments_are_not_lost(self):
        def worker():
            for _ in range(1000):
                self.registry.inc("hits")

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(self.registry.snapshot()["counters"]["hits"], 8000)


class GameSessionMetricsTests(unittest.TestCase):
    def setUp(self):
        metrics.reset()
        self.sessions = []

    def tearDown(self):
        for session in self.sessions:
            session.close()
        metrics.reset()

    def session(self):
        session = GameSession(FakeSocket(), ("synthetic", 1))
        self.sessions.append(session)
        return session

    def test_session_and_queue_metrics_track_lifecycle(self):
        session = self.session()
        self.assertTrue(session.send(1002, b"abc", 1, True))
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["counters"]["ofps.sessions.created_total"], 1)
        self.assertEqual(snapshot["counters"]["ofps.network.send_queue_tasks"], 1)
        self.assertEqual(snapshot["counters"]["ofps.network.send_queue_bytes"], 3)

        session.close()
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["counters"]["ofps.sessions.closed_total"], 1)
        self.assertEqual(snapshot["counters"]["ofps.network.send_queue_tasks"], 0)
        self.assertEqual(snapshot["counters"]["ofps.network.send_queue_bytes"], 0)

    def test_send_loop_records_wire_bytes_and_packets(self):
        session = self.session()
        session.send(1002, b"abc", 1, True)
        sender = threading.Thread(target=session._send_loop, daemon=True)
        sender.start()
        self.assertTrue(session.socket.send_entered.wait(1.0))
        session.close()
        sender.join(1.0)
        self.assertFalse(sender.is_alive())

        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["counters"]["ofps.network.packets_sent_total"], 1)
        self.assertGreater(snapshot["counters"]["ofps.network.bytes_sent_total"], 3)

    def test_bulk_position_uses_separate_send_lane(self):
        session = self.session()
        self.assertTrue(
            session.send(MsgId.PlayerSceneSyncDataNotice, b"pos", 1, True)
        )
        self.assertEqual(len(session._send_queue), 0)
        self.assertEqual(len(session._bulk_send_queue), 1)
        snapshot = metrics.snapshot()
        self.assertEqual(
            snapshot["counters"]["ofps.network.bulk_send_queue_tasks"], 1
        )
        self.assertEqual(snapshot["counters"]["ofps.network.send_queue_tasks"], 1)

    def test_send_loop_drains_normal_and_bulk_lanes(self):
        session = self.session()
        session.send(1002, b"normal", 1, True)
        session.send(MsgId.PlayerSceneSyncDataNotice, b"bulk", 2, True)
        sender = threading.Thread(target=session._send_loop, daemon=True)
        sender.start()
        self.assertTrue(session.socket.send_entered.wait(1.0))
        session.close()
        sender.join(1.0)
        self.assertFalse(sender.is_alive())
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["counters"]["ofps.network.packets_sent_total"], 2)
        self.assertEqual(snapshot["counters"]["ofps.network.send_queue_tasks"], 0)
        self.assertEqual(
            snapshot["counters"]["ofps.network.bulk_send_queue_tasks"], 0
        )

    def test_process_buffer_records_packet_and_handler_timing(self):
        session = self.session()
        session._recv_buf[: len(_frame(1007))] = _frame(1007)
        session._recv_len = len(_frame(1007))
        with patch.object(PacketFactory, "process_packet", return_value=True):
            session._process_buffer()

        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["counters"]["ofps.network.packets_received_total"], 1)
        self.assertEqual(
            snapshot["timers"]["ofps.network.handler_duration_seconds"]["count"], 1
        )


class NoticeSyncMetricsTests(unittest.TestCase):
    def setUp(self):
        metrics.reset()

    def tearDown(self):
        metrics.reset()

    def test_cycle_metrics_record_queue_and_channel_counts(self):
        notice_sync._record_cycle_metrics(
            use_time=0.02,
            active_sessions=3,
            channel_count=2,
            action_count=4,
            scene_count=5,
            chat_count=6,
            position_count=7,
        )
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["counters"]["ofps.notice.cycles_total"], 1)
        self.assertEqual(snapshot["counters"]["ofps.notice.action_messages"], 4)
        self.assertEqual(snapshot["counters"]["ofps.notice.scene_messages"], 5)
        self.assertEqual(snapshot["counters"]["ofps.notice.chat_messages"], 6)
        self.assertEqual(snapshot["counters"]["ofps.notice.position_players"], 7)
        self.assertEqual(snapshot["gauges"]["ofps.notice.active_sessions"], 3)
        self.assertEqual(snapshot["gauges"]["ofps.notice.channels"], 2)

    def test_over_budget_cycle_is_counted(self):
        with patch.object(notice_sync, "max_tps", 1000):
            notice_sync._record_cycle_metrics(0.01, 1, 1, 0, 0, 0, 0)
        self.assertEqual(
            metrics.snapshot()["counters"]["ofps.notice.over_budget_total"], 1
        )


class PlayerPingMetricsTests(unittest.TestCase):
    def setUp(self):
        metrics.reset()

    def tearDown(self):
        metrics.reset()

    def test_ping_records_request_and_processing_time(self):
        sent = []

        class Session:
            def send(self, msg_id, message, packet_id):
                sent.append((msg_id, message, packet_id))

        request = PlayerPingReq(client_time_ms=1234)
        PlayerPingHandler().handle(Session(), request.SerializeToString(), 9)

        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["counters"]["ofps.ping.requests_total"], 1)
        self.assertEqual(
            snapshot["timers"]["ofps.ping.processing_duration_seconds"]["count"], 1
        )
        self.assertEqual(sent[0][2], 9)


if __name__ == "__main__":
    unittest.main()
