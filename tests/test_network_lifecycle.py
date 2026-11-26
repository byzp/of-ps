import contextlib
import os
import socket
import struct
import threading
import time
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cramjam import snappy

from config import Config
import http_server.server as http_server
import main as main_module
from network.game_server import GameServer
from network.game_session import GameSession, _ProtocolError
from network.msg_id import MsgId
from network.packet_factory import PacketFactory
import network.remote_link as remote_link
from proto.net_pb2 import (
    LinkMessage,
    PacketHead,
    PlayerInfo,
    PlayerLoginRsp,
    StatusCode,
    VerifyLoginTokenRsp,
)
import server.notice_sync as notice_sync
from server.scene_data import _session_list, lock_session


def _frame(msg_id, body=b"", packet_id=1, flag=0, body_len=None):
    head = PacketHead(
        msg_id=msg_id,
        packet_id=packet_id,
        flag=flag,
        body_len=len(body) if body_len is None else body_len,
    ).SerializeToString()
    return struct.pack(">H", len(head)) + head + body


def _recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection closed")
        data.extend(chunk)
    return bytes(data)


def _recv_packet(sock):
    header_len = struct.unpack(">H", _recv_exact(sock, 2))[0]
    head = PacketHead()
    head.ParseFromString(_recv_exact(sock, header_len))
    body = _recv_exact(sock, head.body_len)
    if head.flag == 1:
        body = snappy.decompress_raw(body)
    return head, body


def _reserve_tcp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _reserve_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _tcp_pair():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client = socket.create_connection(listener.getsockname(), timeout=1.0)
        server, _ = listener.accept()
    client.settimeout(1.0)
    server.settimeout(1.0)
    return client, server


class FakeSocket:
    def __init__(self):
        self.closed_event = threading.Event()
        self.send_entered = threading.Event()
        self.lock = threading.Lock()
        self.shutdown_calls = 0
        self.close_calls = 0
        self.timeout = None
        self.block_send = False

    def setsockopt(self, *args):
        pass

    def settimeout(self, timeout):
        self.timeout = timeout

    def shutdown(self, how):
        with self.lock:
            self.shutdown_calls += 1
        self.closed_event.set()

    def close(self):
        with self.lock:
            self.close_calls += 1
        self.closed_event.set()

    def sendall(self, data):
        self.send_entered.set()
        if self.block_send:
            if not self.closed_event.wait(0.2):
                raise socket.timeout("synthetic slow reader")
            return
        if self.closed_event.is_set():
            raise OSError("closed")


class GameSessionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.old_sessions = list(_session_list)
        _session_list.clear()
        self.sessions = []

    def tearDown(self):
        for session in self.sessions:
            session.close()
        with lock_session:
            _session_list[:] = self.old_sessions

    def session(self, verified=True):
        sock = FakeSocket()
        session = GameSession(sock, ("synthetic", 1))
        session.verified = verified
        self.sessions.append(session)
        return session

    def feed(self, session, data):
        if len(data) > len(session._recv_buf):
            session._ensure_recv_capacity(len(data))
        session._recv_buf[: len(data)] = data
        session._recv_len = len(data)

    def test_concurrent_close_is_idempotent(self):
        session = self.session()
        session.send(1002, b"abc", 1, True)
        barrier = threading.Barrier(9)

        def close():
            barrier.wait()
            session.close()

        threads = [threading.Thread(target=close) for _ in range(8)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(1.0)
            self.assertFalse(thread.is_alive())
        self.assertFalse(session.running)
        self.assertTrue(session.closed.is_set())
        self.assertEqual(session.socket.shutdown_calls, 1)
        self.assertEqual(session.socket.close_calls, 1)
        self.assertEqual(len(session._send_queue), 0)
        self.assertEqual(session._send_queued_bytes, 0)

    def test_exact_message_boundary_is_dispatched(self):
        session = self.session()
        with patch.object(GameSession, "MAX_MESSAGE_BYTES", 32), \
             patch.object(GameSession, "MAX_WIRE_BODY_BYTES", 32), \
             patch.object(GameSession, "MAX_PACKET_BYTES", 2 + 1024 + 32), \
             patch.object(PacketFactory, "process_packet", return_value=True) as process:
            self.feed(session, _frame(1007, b"x" * 32))
            session._process_buffer()
        process.assert_called_once()
        self.assertEqual(process.call_args.args[1], b"x" * 32)
        self.assertEqual(session._recv_len, 0)

    def test_oversized_declared_body_is_rejected_before_body_arrives(self):
        session = self.session()
        data = _frame(1007, body_len=GameSession.MAX_WIRE_BODY_BYTES + 1)
        self.feed(session, data)
        with patch.object(PacketFactory, "process_packet") as process:
            with self.assertRaisesRegex(_ProtocolError, "body exceeds"):
                session._process_buffer()
        process.assert_not_called()

    def test_large_incomplete_packet_grows_only_to_bounded_capacity(self):
        session = self.session()
        with patch.object(GameSession, "MAX_MESSAGE_BYTES", 100000), \
             patch.object(GameSession, "MAX_WIRE_BODY_BYTES", 100000), \
             patch.object(GameSession, "MAX_PACKET_BYTES", 2 + 1024 + 100000):
            data = _frame(1007, body_len=90000)
            self.feed(session, data)
            session._process_buffer()
        self.assertGreaterEqual(len(session._recv_buf), len(data))
        self.assertLessEqual(len(session._recv_buf), GameSession.MAX_PACKET_BYTES)
        self.assertEqual(session._recv_len, len(data))

    def test_malformed_header_and_flags_are_rejected(self):
        for data in (
            struct.pack(">H", 1) + b"\xff",
            _frame(1007, flag=2),
            struct.pack(">H", GameSession.MAX_HEADER_BYTES + 1),
        ):
            session = self.session()
            self.feed(session, data)
            with self.assertRaises(_ProtocolError):
                session._process_buffer()

    def test_unauthorized_message_is_rejected(self):
        session = self.session(verified=False)
        self.feed(session, _frame(1003))
        with patch.object(PacketFactory, "process_packet") as process:
            with self.assertRaisesRegex(_ProtocolError, "unauthorized"):
                session._process_buffer()
        process.assert_not_called()

    def test_snappy_bomb_is_rejected_before_decompression(self):
        session = self.session()
        compressed = b"\x81\x01"  # snappy raw length 129
        with patch.object(GameSession, "MAX_MESSAGE_BYTES", 128), \
             patch("network.game_session.snappy.decompress_raw") as decompress:
            self.feed(session, _frame(1007, compressed, flag=1))
            with self.assertRaisesRegex(_ProtocolError, "decompressed body"):
                session._process_buffer()
        decompress.assert_not_called()

    def test_valid_compressed_packet_is_dispatched(self):
        session = self.session()
        body = b"compress-me" * 300
        compressed = snappy.compress_raw(body)
        with patch.object(PacketFactory, "process_packet", return_value=True) as process:
            self.feed(session, _frame(1007, compressed, flag=1))
            session._process_buffer()
        self.assertEqual(process.call_args.args[1], body)

    def test_send_queue_overflow_closes_slow_session(self):
        session = self.session()
        with patch.object(GameSession, "MAX_SEND_QUEUE_BYTES", 4):
            self.assertTrue(session.send(1002, b"abc", 1, True))
            self.assertTrue(session.send(1002, b"d", 2, True))
            self.assertFalse(session.send(1002, b"e", 3, True))
        self.assertFalse(session.running)
        self.assertEqual(len(session._send_queue), 0)

    def test_oversized_outgoing_message_is_rejected_without_closing(self):
        session = self.session()
        with patch.object(GameSession, "MAX_MESSAGE_BYTES", 4):
            self.assertFalse(session.send(1002, b"12345", 1, True))
        self.assertTrue(session.running)

    def test_external_close_unblocks_sender(self):
        session = self.session()
        session.socket.block_send = True
        session.send(1002, b"abc", 1, True)
        sender = threading.Thread(target=session._send_loop, daemon=True)
        sender.start()
        self.assertTrue(session.socket.send_entered.wait(1.0))
        session.close()
        sender.join(1.0)
        self.assertFalse(sender.is_alive())

    def test_idle_unauthenticated_connection_times_out_and_unregisters(self):
        client, server = _tcp_pair()
        self.addCleanup(client.close)
        session = GameSession(server, ("local", 1))
        self.sessions.append(session)
        with lock_session:
            _session_list.append(session)
        with patch.object(GameSession, "AUTH_TIMEOUT", 0.05), \
             patch.object(GameSession, "_READ_POLL_INTERVAL", 0.01):
            worker = threading.Thread(target=session.run)
            worker.start()
            self.assertTrue(session.wait_closed(1.0))
            worker.join(1.0)
        self.assertFalse(worker.is_alive())
        self.assertFalse(session._send_thread.is_alive())
        with lock_session:
            self.assertNotIn(session, _session_list)

    def test_partial_packet_cannot_be_kept_alive_by_trickled_bytes(self):
        client, server = _tcp_pair()
        self.addCleanup(client.close)
        session = GameSession(server, ("local", 1))
        self.sessions.append(session)
        client.sendall(b"\x00")
        with patch.object(GameSession, "AUTH_TIMEOUT", 1.0), \
             patch.object(GameSession, "PACKET_TIMEOUT", 0.05), \
             patch.object(GameSession, "_READ_POLL_INTERVAL", 0.01):
            worker = threading.Thread(target=session.run)
            worker.start()
            self.assertTrue(session.wait_closed(1.0))
            worker.join(1.0)
        self.assertFalse(session.running)


class PacketFactoryLifecycleTests(unittest.TestCase):
    def tearDown(self):
        PacketFactory.shutdown()

    def test_pending_limit_closes_session_instead_of_growing_queue(self):
        entered = threading.Event()
        release = threading.Event()

        class Handler:
            def handle(self, session, data, packet_id):
                entered.set()
                release.wait(1.0)

        sock = FakeSocket()
        session = GameSession(sock, ("synthetic", 2))
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            with patch.object(PacketFactory, "_handlers", {99: Handler()}), \
                 patch.object(PacketFactory, "_executor", executor), \
                 patch.object(PacketFactory, "_accepting", True), \
                 patch.object(PacketFactory, "_pending", set()), \
                 patch.object(PacketFactory, "MAX_PENDING_PACKETS", 1):
                self.assertTrue(PacketFactory.process_packet(99, b"", 1, session))
                self.assertTrue(entered.wait(1.0))
                self.assertFalse(PacketFactory.process_packet(99, b"", 2, session))
                self.assertFalse(session.running)
                release.set()
        finally:
            release.set()
            executor.shutdown(wait=True, cancel_futures=True)
            session.close()

    def test_shutdown_waits_for_running_handler(self):
        entered = threading.Event()
        release = threading.Event()

        class Handler:
            def handle(self, session, data, packet_id):
                entered.set()
                release.wait(1.0)

        sock = FakeSocket()
        session = GameSession(sock, ("synthetic", 3))
        executor = ThreadPoolExecutor(max_workers=1)
        finished = threading.Event()

        def shutdown():
            PacketFactory.shutdown()
            finished.set()

        try:
            with patch.object(PacketFactory, "_handlers", {99: Handler()}), \
                 patch.object(PacketFactory, "_executor", executor), \
                 patch.object(PacketFactory, "_accepting", True), \
                 patch.object(PacketFactory, "_pending", set()):
                PacketFactory.process_packet(99, b"", 1, session)
                self.assertTrue(entered.wait(1.0))
                worker = threading.Thread(target=shutdown)
                worker.start()
                self.assertFalse(finished.wait(0.05))
                release.set()
                worker.join(1.0)
                self.assertTrue(finished.is_set())
        finally:
            release.set()
            session.close()


class GameServerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.old_sessions = list(_session_list)
        _session_list.clear()
        self.servers = []
        self.seen_sessions = []

    def tearDown(self):
        for server in self.servers:
            if not server.stopped:
                server.stop()
        with lock_session:
            _session_list[:] = self.old_sessions

    def start_server(self, port, stack, max_connections=64, workers=4):
        stack.enter_context(patch.object(Config, "GAME_SERVER_IP", "127.0.0.1"))
        stack.enter_context(patch.object(Config, "GAME_SERVER_PORT", port))
        stack.enter_context(patch.object(Config, "SESSION_POOL_MAX_WORKERS", workers))
        stack.enter_context(patch.object(PacketFactory, "initialize_handlers"))
        stack.enter_context(patch.object(PacketFactory, "shutdown"))
        stack.enter_context(patch.object(notice_sync, "init", return_value=None))
        stack.enter_context(patch.object(notice_sync, "stop"))
        stack.enter_context(patch.object(GameSession, "AUTH_TIMEOUT", 1.0))
        server = GameServer()
        server.MAX_CONNECTIONS = max_connections
        server.ACCEPT_TIMEOUT = 0.02
        self.servers.append(server)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        self.assertTrue(server.wait_started(2.0))
        return server, thread

    def test_repeated_login_disconnect_and_same_port_restart(self):
        port = _reserve_tcp_port()

        def process(msg_id, body, packet_id, session):
            if msg_id == MsgId.VerifyLoginTokenReq:
                session.verified = True
                session.player_id = 1000000 + packet_id
                session.send(
                    MsgId.VerifyLoginTokenRsp,
                    VerifyLoginTokenRsp(status=StatusCode.StatusCode_OK),
                    packet_id,
                )
            elif msg_id == MsgId.PlayerLoginReq:
                session.logged_in = True
                session.send(
                    MsgId.PlayerLoginRsp,
                    PlayerLoginRsp(status=StatusCode.StatusCode_OK),
                    packet_id,
                )
                self.seen_sessions.append(session)
            return True

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(PacketFactory, "process_packet", side_effect=process))
            for cycle in range(10):
                server, thread = self.start_server(port, stack)
                self.assertEqual(server.server_socket.getsockname()[1], port)
                for client_index in range(3):
                    for attempt in range(2):
                        client = socket.create_connection(("127.0.0.1", port), timeout=1.0)
                        try:
                            packet_id = cycle * 100 + client_index * 2 + attempt + 1
                            client.sendall(_frame(MsgId.VerifyLoginTokenReq, packet_id=packet_id))
                            head, body = _recv_packet(client)
                            self.assertEqual(head.msg_id, MsgId.VerifyLoginTokenRsp)
                            self.assertEqual(VerifyLoginTokenRsp.FromString(body).status, StatusCode.StatusCode_OK)
                            client.sendall(_frame(MsgId.PlayerLoginReq, packet_id=packet_id + 1))
                            head, body = _recv_packet(client)
                            self.assertEqual(head.msg_id, MsgId.PlayerLoginRsp)
                            self.assertEqual(PlayerLoginRsp.FromString(body).status, StatusCode.StatusCode_OK)
                        finally:
                            if attempt == 0 and cycle % 2:
                                client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                            client.close()

                        deadline = time.monotonic() + 1.0
                        while time.monotonic() < deadline:
                            with lock_session:
                                if not any(not item.remote and item.running for item in _session_list):
                                    break
                            time.sleep(0.005)
                server.stop()
                server.stop()
                thread.join(1.0)
                self.assertFalse(thread.is_alive())
                self.assertTrue(server.stopped)
                with lock_session:
                    self.assertEqual(_session_list, [])

        self.assertEqual(len(self.seen_sessions), 60)
        for session in self.seen_sessions:
            self.assertFalse(session.running)
            self.assertFalse(session._send_thread.is_alive())

    def test_connection_limit_rejects_excess_client(self):
        port = _reserve_tcp_port()
        with contextlib.ExitStack() as stack:
            server, thread = self.start_server(port, stack, max_connections=1)
            first = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            second = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            try:
                second.settimeout(1.0)
                self.assertEqual(second.recv(1), b"")
            finally:
                first.close()
                second.close()
                server.stop()
                thread.join(1.0)

    def test_queued_session_expires_without_waiting_for_a_worker(self):
        port = _reserve_tcp_port()
        with contextlib.ExitStack() as stack:
            server, thread = self.start_server(port, stack, workers=1)
            first = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            second = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            try:
                with patch.object(GameSession, "AUTH_TIMEOUT", 0.1):
                    second.settimeout(1.0)
                    self.assertEqual(second.recv(1), b"")
            finally:
                first.close()
                second.close()
                server.stop()
                thread.join(1.0)

    def test_bind_conflict_does_not_share_port(self):
        port = _reserve_tcp_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
            held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            held.bind(("127.0.0.1", port))
            held.listen(1)
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(Config, "GAME_SERVER_IP", "127.0.0.1"))
                stack.enter_context(patch.object(Config, "GAME_SERVER_PORT", port))
                stack.enter_context(patch.object(PacketFactory, "initialize_handlers"))
                stack.enter_context(patch.object(PacketFactory, "shutdown"))
                server = GameServer()
                self.servers.append(server)
                thread = threading.Thread(target=server.start, daemon=True)
                thread.start()
                with self.assertRaises(RuntimeError):
                    server.wait_started(2.0)
                thread.join(1.0)
                self.assertTrue(server.stopped)
                self.assertIsNotNone(server.startup_error)

    def test_concurrent_stop_calls_wait_for_one_shutdown(self):
        port = _reserve_tcp_port()
        with contextlib.ExitStack() as stack:
            server, thread = self.start_server(port, stack)
            client = socket.create_connection(("127.0.0.1", port), timeout=1.0)
            self.addCleanup(client.close)
            barrier = threading.Barrier(7)
            errors = []

            def stop():
                try:
                    barrier.wait()
                    server.stop()
                except Exception as error:
                    errors.append(error)

            workers = [threading.Thread(target=stop) for _ in range(6)]
            for worker in workers:
                worker.start()
            barrier.wait()
            for worker in workers:
                worker.join(2.0)
                self.assertFalse(worker.is_alive())
            thread.join(1.0)
            self.assertEqual(errors, [])
            self.assertTrue(server.stopped)


class NoticeSyncLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.old_sessions = list(_session_list)
        self.old_sync_stop = notice_sync.sync_stop
        self.old_stop_event = notice_sync._stop_event
        _session_list.clear()

    def tearDown(self):
        notice_sync.stop()
        notice_sync.sync_stop = self.old_sync_stop
        notice_sync._stop_event = self.old_stop_event
        with lock_session:
            _session_list[:] = self.old_sessions

    def test_fatal_loop_error_requests_shutdown_without_hard_exit(self):
        with patch.object(notice_sync, "_thread", None), \
             patch.object(notice_sync, "_stamina_thread", None), \
             patch.object(notice_sync, "_stop_event", threading.Event()), \
             patch.object(notice_sync, "_stopped_event", threading.Event()), \
             patch.object(notice_sync, "sync_stop", False), \
             patch.object(notice_sync, "notice_sync_loop", side_effect=RuntimeError("synthetic")):
            notice_sync.start_loop()
            self.assertTrue(notice_sync.failed())
            self.assertTrue(notice_sync.sync_stop)

    def test_stop_waits_for_final_session_save_and_clears_registry(self):
        entered = threading.Event()
        release = threading.Event()
        cycle_entered = threading.Event()
        session = SimpleNamespace(
            running=True,
            logged_in=True,
            remote=False,
            player_id=1,
            player_name="synthetic",
            scene_id=1,
            channel_id=1,
            chat_channel_id=1,
            send=lambda *args: None,
        )
        with lock_session:
            _session_list.append(session)

        def slow_save(*args):
            entered.set()
            release.wait(1.0)

        loop = threading.Thread(target=notice_sync.notice_sync_loop, daemon=True)
        stopper = threading.Thread(target=notice_sync.stop, daemon=True)
        with patch.object(notice_sync, "_thread", loop), \
             patch.object(notice_sync, "_stamina_thread", None), \
             patch.object(notice_sync, "_stop_event", threading.Event()), \
             patch.object(notice_sync, "_stopped_event", threading.Event()), \
             patch.object(notice_sync, "sync_stop", False), \
             patch.object(notice_sync, "_save_local_session", side_effect=slow_save) as save, \
             patch.object(notice_sync, "_cleanup_disconnected_locked", side_effect=lambda timestamp: cycle_entered.set()):
            loop.start()
            self.assertTrue(cycle_entered.wait(1.0))
            stopper.start()
            self.assertTrue(entered.wait(1.0))
            self.assertFalse(stopper.join(0.05))
            release.set()
            loop.join(1.0)
            stopper.join(1.0)
            self.assertFalse(loop.is_alive())
            self.assertFalse(stopper.is_alive())
            save.assert_called_once()
        self.assertFalse(session.logged_in)
        with lock_session:
            self.assertEqual(_session_list, [])


class FakeKCP:
    instances = []

    def __init__(self, **kwargs):
        self.close_calls = 0
        self.sessions = {}
        self.__class__.instances.append(self)

    def start_update_loop(self, interval_ms):
        pass

    def close_all(self):
        self.close_calls += 1
        self.sessions.clear()

    def send(self, conv, data):
        return True

    def remove(self, conv):
        return self.sessions.pop(conv, None) is not None

    def get_or_create(self, conv):
        return SimpleNamespace(send=lambda data: None)

    def input(self, data):
        return 0


class RemoteLinkLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.old_sessions = list(_session_list)
        _session_list.clear()
        remote_link.stop()
        FakeKCP.instances.clear()

    def tearDown(self):
        remote_link.stop()
        with lock_session:
            _session_list[:] = self.old_sessions

    def test_stop_is_idempotent_joins_threads_and_removes_remote_sessions(self):
        port = _reserve_udp_port()
        remote = remote_link.RemoteSession("peer", PlayerInfo(player_id=1, player_name="remote"))
        with lock_session:
            _session_list.append(remote)
        with patch.object(Config, "LINK_OTHER_SERVER", True), \
             patch.object(Config, "LINK_LISTEN", ("127.0.0.1", port)), \
             patch.object(Config, "LINK_POOL", []), \
             patch.object(remote_link, "KCP_IMPORT_FAILED", False), \
             patch.object(remote_link, "KCPManager", FakeKCP, create=True), \
             patch.object(remote_link, "_load_cache", return_value=[]):
            remote_link.init()
            listen_thread = remote_link._listen_thread
            maintenance_thread = remote_link._maintenance_thread
            self.assertTrue(listen_thread.is_alive())
            self.assertTrue(maintenance_thread.is_alive())
            workers = [threading.Thread(target=remote_link.stop) for _ in range(4)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(2.0)
                self.assertFalse(worker.is_alive())
            self.assertFalse(listen_thread.is_alive())
            self.assertFalse(maintenance_thread.is_alive())
            self.assertEqual(FakeKCP.instances[0].close_calls, 1)
            self.assertFalse(remote.running)
            with lock_session:
                self.assertEqual(_session_list, [])
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rebound:
                rebound.bind(("127.0.0.1", port))
            remote_link.stop()

    def test_oversized_link_message_is_rejected_before_decompression(self):
        with patch.object(remote_link, "MAX_LINK_MESSAGE_BYTES", 128), \
             patch.object(remote_link.snappy, "decompress_raw") as decompress:
            with self.assertRaisesRegex(ValueError, "exceeds size"):
                remote_link._unpack(b"\x81\x01")
        decompress.assert_not_called()

    def test_disconnected_link_queue_has_byte_limit(self):
        message = LinkMessage(id="bounded")
        with patch.object(remote_link, "_stopped", threading.Event()), \
             patch.object(remote_link, "_links", {}), \
             patch.object(remote_link, "_pack", return_value=b"xx"), \
             patch.object(remote_link, "MAX_QUEUED_BYTES", 1), \
             patch.object(remote_link, "_connect") as connect:
            remote_link._send_to(message, ("127.0.0.1", 1))
            self.assertEqual(remote_link._links[("127.0.0.1", 1)].queued, [])
            connect.assert_not_called()


class HttpServerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.old_host = Config.HTTP_HOST
        self.old_port = Config.HTTP_PORT
        self.old_server = http_server._server
        self.old_stop = http_server._stop_requested
        self.old_stopped = http_server._stopped
        self.old_ever = http_server._ever_started
        self.old_error = http_server._startup_error
        http_server._server = None
        http_server._stop_requested = threading.Event()
        http_server._stopped = threading.Event()
        http_server._ever_started = threading.Event()
        http_server._startup_error = None
        self.threads = []

    def tearDown(self):
        http_server.stop()
        for thread in self.threads:
            thread.join(2.0)
        Config.HTTP_HOST = self.old_host
        Config.HTTP_PORT = self.old_port
        http_server._server = self.old_server
        http_server._stop_requested = self.old_stop
        http_server._stopped = self.old_stopped
        http_server._ever_started = self.old_ever
        http_server._startup_error = self.old_error

    def start(self):
        thread = threading.Thread(target=http_server.start, daemon=True)
        self.threads.append(thread)
        thread.start()
        self.assertTrue(http_server.wait_started(2.0))
        return thread

    def test_stop_before_start_cannot_late_start_server(self):
        http_server.stop()
        with patch.object(http_server.uvicorn, "Server") as server:
            http_server.start()
        server.assert_not_called()
        self.assertTrue(http_server.wait_stopped(0.1))

    def test_loopback_restart_reuses_port_and_rejects_oversized_body(self):
        port = _reserve_tcp_port()
        Config.HTTP_HOST = "127.0.0.1"
        Config.HTTP_PORT = port
        for _ in range(2):
            thread = self.start()
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1.0) as response:
                self.assertEqual(response.status, 200)
            with socket.create_connection(("127.0.0.1", port), timeout=1.0) as client:
                client.sendall(
                    b"POST /api/login HTTP/1.1\r\n"
                    b"Host: localhost\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: 65537\r\n\r\n"
                )
                response = client.recv(4096)
                self.assertIn(b"413", response)
            http_server.stop()
            http_server.stop()
            thread.join(2.0)
            self.assertFalse(thread.is_alive())
            self.assertTrue(http_server.wait_stopped(0.1))


class MainShutdownTests(unittest.TestCase):
    def run_main(self, db_exit_side_effect=None):
        stop_event = threading.Event()
        stop_event.set()
        order = []

        class FakeGameServer:
            running = True
            startup_error = None

            def start(self):
                pass

            def wait_started(self, timeout):
                return True

            def stop(self):
                order.append("game-stop")

        fake_http = SimpleNamespace(
            start=lambda: order.append("http-start"),
            stop=lambda: order.append("http-stop"),
            wait_started=lambda timeout: True,
            startup_error=lambda: None,
            HTTP_GRACEFUL_SHUTDOWN=0.1,
        )

        def db_exit():
            order.append("db-exit")
            if db_exit_side_effect is not None:
                db_exit_side_effect()

        with patch.object(main_module.signal, "signal"), \
             patch.object(main_module.cmd, "start", return_value=stop_event), \
             patch.object(main_module.res_loader, "init"), \
             patch.object(main_module.db, "init"), \
             patch.object(main_module.db, "exit", side_effect=db_exit), \
             patch.object(main_module.photo_share, "load"), \
             patch.object(main_module.photo_share, "save", side_effect=lambda: order.append("photo-save")), \
             patch.object(main_module, "GameServer", return_value=FakeGameServer()), \
             patch.object(main_module, "http_server", fake_http), \
             patch.object(main_module.remote_link, "init"), \
             patch.object(main_module.remote_link, "stop", side_effect=lambda: order.append("remote-stop")), \
             patch.object(main_module.notice_sync, "failed", return_value=False), \
             patch("os._exit", side_effect=AssertionError("hard exit used")):
            main_module.main()
        return order

    def test_second_signal_during_save_does_not_bypass_persistence(self):
        saved = []

        def exit_and_signal():
            main_module._graceful_exit(2, None)
            main_module._graceful_exit(2, None)
            saved.append(True)

        order = self.run_main(exit_and_signal)
        self.assertEqual(saved, [True])
        self.assertLess(order.index("game-stop"), order.index("photo-save"))
        self.assertLess(order.index("photo-save"), order.index("db-exit"))
        self.assertEqual(order.count("db-exit"), 1)

    def test_startup_failure_still_runs_shutdown_and_database_close(self):
        stop_event = threading.Event()

        class BrokenGameServer:
            running = False
            startup_error = "synthetic"

            def start(self):
                pass

            def wait_started(self, timeout):
                raise RuntimeError("synthetic startup")

            def stop(self):
                pass

        fake_http = SimpleNamespace(
            start=lambda: None,
            stop=lambda: None,
            wait_started=lambda timeout: True,
            startup_error=lambda: None,
            HTTP_GRACEFUL_SHUTDOWN=0.1,
        )
        with patch.object(main_module.signal, "signal"), \
             patch.object(main_module.cmd, "start", return_value=stop_event), \
             patch.object(main_module.res_loader, "init"), \
             patch.object(main_module.db, "init"), \
             patch.object(main_module.db, "exit") as exit_db, \
             patch.object(main_module.photo_share, "load"), \
             patch.object(main_module.photo_share, "save"), \
             patch.object(main_module, "GameServer", return_value=BrokenGameServer()), \
             patch.object(main_module, "http_server", fake_http), \
             patch.object(main_module.remote_link, "stop"):
            with self.assertRaisesRegex(RuntimeError, "synthetic startup"):
                main_module.main()
        exit_db.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
