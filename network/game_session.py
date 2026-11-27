import logging
import select
import socket
import struct
import time
from collections import deque
from threading import Event, Lock, RLock, Thread, current_thread

from cramjam import snappy
from google.protobuf.message import DecodeError, Message

from config import Config
from network.msg_id import MsgId
from network.packet_factory import PacketFactory
from proto.net_pb2 import PacketHead, PosColor, ScenePlayer
from server import lobby_state
from utils import metrics as metrics_registry
from utils.rate_limit import SessionRateLimiter

logger = logging.getLogger(__name__)

# 预编译常量
_HEADER_STRUCT = struct.Struct(">H")
_UNAUTH_CMDS = frozenset((1001, 1007, 2201, 2203))
_NOSEQ_CMDS = frozenset((1002, 1004, 1006, 1008))
_COMPRESS_THRESHOLD = Config.COMPRESS_THRESHOLD

id_to_name = {
    v: k
    for k, v in vars(MsgId).items()
    if not k.startswith("__") and isinstance(v, int)
}


class _ProtocolError(Exception):
    pass


def _snappy_uncompressed_length(data):
    """Read snappy's raw-stream length without allocating the decoded body."""
    value = 0
    shift = 0
    for index, byte in enumerate(data[:5]):
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
        shift += 7
    raise _ProtocolError("invalid snappy length")


class SendTask:
    __slots__ = ("msg_id", "data", "packet_id", "is_bin")

    def __init__(self, msg_id, data, packet_id, is_bin):
        self.msg_id = msg_id
        self.data = data
        self.packet_id = packet_id
        self.is_bin = is_bin


class GameSession:
    __slots__ = (
        "socket",
        "address",
        "_recv_buf",
        "_recv_len",
        "_recv_started",
        "created_at",
        "run_started",
        "_send_queue",
        "_bulk_send_queue",
        "_send_lock",
        "_send_event",
        "_send_thread",
        "_send_queued_bytes",
        "_bulk_send_queued_bytes",
        "_close_lock",
        "closed",
        "_seq_id",
        "_write_head_buf",
        # 玩家状态
        "player_id",
        "player_name",
        "scene_id",
        "channel_id",
        "chat_channel_id",
        "avatar_id",
        "badge_id",
        "scene_player",
        "temp_pack",
        "pos",
        "drop_items",
        "drop_lock",
        "color_data",
        "fishing",
        "fishing_token",
        "fishing_cost",
        "dungeon",
        "dungeon_token",
        "quests",
        "running",
        "verified",
        "logged_in",
        "remote",
        "rate_limiter",
    )

    HEADER_LENGTH = 2
    _RECV_BUF_SIZE = 65536
    _SEND_BATCH_LIMIT = 50
    _SEND_BATCH_BYTES = 1024 * 1024
    _READ_POLL_INTERVAL = 0.5

    # Network trust boundaries.  A packet may temporarily occupy the wire-body
    # allowance plus a small snappy overhead, but handlers never receive more
    # than MAX_MESSAGE_BYTES.
    MAX_HEADER_BYTES = 1024
    MAX_MESSAGE_BYTES = 4 * 1024 * 1024
    MAX_WIRE_BODY_BYTES = MAX_MESSAGE_BYTES + 64 * 1024
    MAX_PACKET_BYTES = HEADER_LENGTH + MAX_HEADER_BYTES + MAX_WIRE_BODY_BYTES
    MAX_SEND_QUEUE_BYTES = 8 * 1024 * 1024
    MAX_SEND_QUEUE_TASKS = 2048

    AUTH_TIMEOUT = 15.0
    IDLE_TIMEOUT = 90.0
    PACKET_TIMEOUT = 15.0
    WRITE_TIMEOUT = 10.0

    def __init__(self, client_socket: socket.socket, address):
        metrics_registry.metrics.inc("ofps.sessions.created_total")
        self.socket = client_socket
        self.address = address
        self._close_lock = Lock()
        self.closed = Event()

        # TCP优化
        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 524288)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)

        self._recv_buf = bytearray(self._RECV_BUF_SIZE)
        self._recv_len = 0
        self._recv_started = 0.0
        self.created_at = time.monotonic()
        self.run_started = False

        self._send_queue = deque()
        self._bulk_send_queue = deque()
        self._send_lock = Lock()
        self._send_event = Event()
        self._send_thread = None
        self._send_queued_bytes = 0
        self._bulk_send_queued_bytes = 0

        self._write_head_buf = bytearray(128)
        self._seq_id = 1

        self.player_id = 0
        self.player_name = ""
        self.scene_id = 1
        self.channel_id = 1
        self.chat_channel_id = 1
        self.avatar_id = 41101
        self.badge_id = 0
        self.scene_player = ScenePlayer()
        self.temp_pack = []
        self.pos = {}
        self.drop_items = {}
        self.drop_lock = RLock()
        self.color_data = [None, None, PosColor()]
        self.fishing = False
        self.fishing_token = ""
        self.fishing_cost = None
        self.dungeon = [0, 0, 0, -1]
        self.dungeon_token = ""
        self.quests = {}

        self.running = True
        self.verified = False
        self.logged_in = False
        self.remote = False
        self.rate_limiter = SessionRateLimiter(
            {
                "chat": (
                    Config.CHAT_RATE_LIMIT_PER_SEC,
                    Config.CHAT_RATE_LIMIT_BURST,
                ),
                "action": (
                    Config.ACTION_RATE_LIMIT_PER_SEC,
                    Config.ACTION_RATE_LIMIT_BURST,
                ),
                "emoji": (
                    Config.EMOJI_RATE_LIMIT_PER_SEC,
                    Config.EMOJI_RATE_LIMIT_BURST,
                ),
            }
        )

    def run(self):
        self.run_started = True
        if not self.running:
            self.closed.set()
            return

        try:
            self._send_thread = Thread(
                target=self._send_loop,
                daemon=True,
                name=f"sender-{self.address}",
            )
            self._send_thread.start()
            # sendall is bounded independently of the read loop's deadlines.
            self.socket.settimeout(self.WRITE_TIMEOUT)
        except Exception:
            logger.exception("Unable to start session worker")
            self.close()
            self.closed.set()
            return

        sock = self.socket
        last_activity = self.created_at

        try:
            while self.running:
                now = time.monotonic()
                if self._recv_len:
                    # A peer trickling bytes cannot keep a partial frame alive
                    # forever.  This deadline is independent of idle traffic.
                    deadline = self._recv_started + self.PACKET_TIMEOUT
                elif not self.verified:
                    # Unauthenticated keepalives do not extend the login window.
                    deadline = self.created_at + self.AUTH_TIMEOUT
                else:
                    deadline = last_activity + self.IDLE_TIMEOUT

                remaining = deadline - now
                if remaining <= 0:
                    logger.debug("Session deadline expired: %s", self.address)
                    break

                try:
                    readable, _, exceptional = select.select(
                        [sock], [], [], min(remaining, self._READ_POLL_INTERVAL)
                    )
                except (OSError, ValueError):
                    break
                if exceptional or not self.running:
                    break
                if not readable:
                    continue

                available = len(self._recv_buf) - self._recv_len
                if available <= 0:
                    self._ensure_recv_capacity(self._recv_len + 1)
                    available = len(self._recv_buf) - self._recv_len

                try:
                    n = sock.recv_into(memoryview(self._recv_buf)[self._recv_len :])
                except socket.timeout:
                    continue
                if n == 0:
                    break
                metrics_registry.metrics.inc("ofps.network.bytes_received_total", n)
                metrics_registry.metrics.inc("ofps.network.recv_calls_total")
                if self._recv_len == 0:
                    self._recv_started = time.monotonic()
                self._recv_len += n
                last_activity = time.monotonic()
                self._process_buffer()
        except _ProtocolError as error:
            metrics_registry.metrics.inc("ofps.network.protocol_errors_total")
            logger.warning("Protocol error from %s: %s", self.address, error)
        except socket.timeout:
            logger.debug("Socket timeout: %s", self.address)
        except OSError:
            pass
        except Exception:
            logger.exception("Session error: %s", self.address)
        finally:
            self.close()
            sender = self._send_thread
            if sender is not None and sender is not current_thread():
                sender.join(timeout=self.WRITE_TIMEOUT + 1.0)
            self._unregister()
            self.closed.set()

    def _ensure_recv_capacity(self, required):
        if required <= len(self._recv_buf):
            return
        if required > self.MAX_PACKET_BYTES:
            raise _ProtocolError("packet exceeds receive limit")
        new_size = min(self.MAX_PACKET_BYTES, max(len(self._recv_buf) * 2, required))
        new_buffer = bytearray(new_size)
        new_buffer[: self._recv_len] = self._recv_buf[: self._recv_len]
        self._recv_buf = new_buffer

    def _process_buffer(self):
        buf = self._recv_buf
        pos = 0
        end = self._recv_len

        while self.running and pos + self.HEADER_LENGTH <= end:
            hlen = _HEADER_STRUCT.unpack_from(buf, pos)[0]
            if not 0 < hlen <= self.MAX_HEADER_BYTES:
                raise _ProtocolError("invalid packet header length")

            hend = pos + self.HEADER_LENGTH + hlen
            if hend > end:
                break

            head = PacketHead()
            try:
                head.ParseFromString(bytes(memoryview(buf)[pos + self.HEADER_LENGTH : hend]))
            except DecodeError as error:
                raise _ProtocolError("malformed packet header") from error

            if head.body_len > self.MAX_WIRE_BODY_BYTES:
                raise _ProtocolError("body exceeds receive limit")
            if not self.verified and head.msg_id not in _UNAUTH_CMDS:
                raise _ProtocolError("unauthorized message")

            pend = hend + head.body_len
            if pend > self.MAX_PACKET_BYTES:
                raise _ProtocolError("packet exceeds receive limit")
            if pend > end:
                self._ensure_recv_capacity(pend)
                break

            body = bytes(memoryview(buf)[hend:pend])
            if head.flag == 1:
                try:
                    raw_len = _snappy_uncompressed_length(body)
                    if raw_len > self.MAX_MESSAGE_BYTES:
                        raise _ProtocolError("decompressed body exceeds receive limit")
                    body = bytes(snappy.decompress_raw(body))
                except _ProtocolError:
                    raise
                except Exception as error:
                    raise _ProtocolError("invalid compressed body") from error
                if len(body) != raw_len or len(body) > self.MAX_MESSAGE_BYTES:
                    raise _ProtocolError("invalid decompressed body length")
            elif head.flag != 0:
                raise _ProtocolError("unsupported packet flags")
            elif len(body) > self.MAX_MESSAGE_BYTES:
                raise _ProtocolError("body exceeds receive limit")

            if head.msg_id not in Config.DEBUG_PACKET_PASS:
                logger.debug("Received message: %s", id_to_name.get(head.msg_id))

            metrics_registry.metrics.inc("ofps.network.packets_received_total")
            try:
                lobby_state.assert_host_authority()
            except lobby_state.StaleEpochError:
                metrics_registry.metrics.inc("ofps.lobby.stale_host_requests_total")
                logger.warning("Rejecting packet from %s: host lease expired", self.address)
                self.running = False
                return
            handler_started = time.perf_counter()
            accepted = PacketFactory.process_packet(
                head.msg_id, body, head.packet_id, self
            )
            metrics_registry.metrics.observe(
                "ofps.network.handler_duration_seconds",
                time.perf_counter() - handler_started,
            )
            if accepted is False or not self.running:
                return
            pos = pend

        if pos > 0:
            rem = end - pos
            if rem > 0:
                self._recv_buf[:rem] = self._recv_buf[pos:end]
            self._recv_len = rem

    def send(self, msg_id: int, message: Message, packet_id: int, is_bin: bool = False):
        if msg_id not in Config.DEBUG_PACKET_PASS:
            logger.debug("Sending message: %s", id_to_name.get(msg_id))
        if not self.running:
            return False

        # Detach bytes-like payloads from caller-owned mutable buffers.
        data_bytes = bytes(message) if is_bin else message.SerializeToString()
        if len(data_bytes) > self.MAX_MESSAGE_BYTES:
            logger.warning("Outgoing message %s exceeds size limit", msg_id)
            return False

        task = SendTask(msg_id, data_bytes, packet_id, is_bin)
        overflow = False
        bulk = msg_id == MsgId.PlayerSceneSyncDataNotice
        with self._send_lock:
            # close() sets running before taking this lock, so a producer cannot
            # enqueue behind a completed close.
            if not self.running:
                return False
            total_tasks = len(self._send_queue) + len(self._bulk_send_queue)
            total_bytes = self._send_queued_bytes + self._bulk_send_queued_bytes
            if (
                total_tasks >= self.MAX_SEND_QUEUE_TASKS
                or total_bytes + len(data_bytes) > self.MAX_SEND_QUEUE_BYTES
            ):
                overflow = True
            elif bulk:
                self._bulk_send_queue.append(task)
                self._bulk_send_queued_bytes += len(data_bytes)
                metrics_registry.metrics.inc("ofps.network.bulk_send_queue_tasks")
                metrics_registry.metrics.inc(
                    "ofps.network.bulk_send_queue_bytes", len(data_bytes)
                )
                if len(self._bulk_send_queue) == 1:
                    self._send_event.set()
            else:
                self._send_queue.append(task)
                self._send_queued_bytes += len(data_bytes)
                if len(self._send_queue) == 1:
                    self._send_event.set()
            if not overflow:
                metrics_registry.metrics.inc("ofps.network.send_queue_tasks")
                metrics_registry.metrics.inc(
                    "ofps.network.send_queue_bytes", len(data_bytes)
                )

        if overflow:
            metrics_registry.metrics.inc("ofps.network.send_queue_overflows_total")
            logger.warning("Send queue overflow: %s", self.address)
            self.close()
            return False
        return True

    def _send_loop(self):
        sock = self.socket
        queue = self._send_queue
        bulk_queue = self._bulk_send_queue
        lock = self._send_lock
        event = self._send_event
        out_buf = bytearray(65536)
        head_proto = PacketHead()

        while self.running:
            event.wait()
            if not self.running:
                break

            tasks = []
            queued_bytes = 0
            with lock:
                normal_limit = max(1, self._SEND_BATCH_LIMIT * 4 // 5)
                while queue and len(tasks) < normal_limit:
                    if tasks and queued_bytes + len(queue[0].data) > self._SEND_BATCH_BYTES:
                        break
                    task = queue.popleft()
                    tasks.append(task)
                    queued_bytes += len(task.data)
                    self._send_queued_bytes -= len(task.data)
                    metrics_registry.metrics.inc("ofps.network.send_queue_tasks", -1)
                    metrics_registry.metrics.inc(
                        "ofps.network.send_queue_bytes", -len(task.data)
                    )
                while bulk_queue and len(tasks) < self._SEND_BATCH_LIMIT:
                    if tasks and queued_bytes + len(bulk_queue[0].data) > self._SEND_BATCH_BYTES:
                        break
                    task = bulk_queue.popleft()
                    tasks.append(task)
                    queued_bytes += len(task.data)
                    self._bulk_send_queued_bytes -= len(task.data)
                    metrics_registry.metrics.inc("ofps.network.bulk_send_queue_tasks", -1)
                    metrics_registry.metrics.inc(
                        "ofps.network.bulk_send_queue_bytes", -len(task.data)
                    )
                    metrics_registry.metrics.inc("ofps.network.send_queue_tasks", -1)
                    metrics_registry.metrics.inc(
                        "ofps.network.send_queue_bytes", -len(task.data)
                    )
                if not queue and not bulk_queue:
                    event.clear()

            if not tasks:
                continue

            current_offset = 0
            for task in tasks:
                if not self.running:
                    break

                body = task.data
                body_len = len(body)
                flag = 0
                if body_len > _COMPRESS_THRESHOLD:
                    compressed = snappy.compress_raw(body)
                    # Never make an incompressible packet larger.
                    if len(compressed) < body_len:
                        body = compressed
                        body_len = len(body)
                        flag = 1

                head_proto.Clear()
                head_proto.msg_id = task.msg_id
                if task.packet_id:
                    head_proto.packet_id = task.packet_id
                head_proto.flag = flag
                head_proto.body_len = body_len
                if task.msg_id in _NOSEQ_CMDS:
                    head_proto.seq_id = 0
                else:
                    head_proto.seq_id = self._seq_id
                    self._seq_id += 1

                h_data = head_proto.SerializeToString()
                h_len = len(h_data)
                if h_len > 0xFFFF:
                    logger.error("Serialized packet header is too large")
                    self.close()
                    return

                total_pkt_len = self.HEADER_LENGTH + h_len + body_len
                required_size = current_offset + total_pkt_len
                if required_size > len(out_buf):
                    new_size = max(len(out_buf) * 2, required_size + 8192)
                    new_buf = bytearray(new_size)
                    new_buf[:current_offset] = out_buf[:current_offset]
                    out_buf = new_buf

                _HEADER_STRUCT.pack_into(out_buf, current_offset, h_len)
                out_buf[current_offset + self.HEADER_LENGTH : current_offset + self.HEADER_LENGTH + h_len] = h_data
                body_start = current_offset + self.HEADER_LENGTH + h_len
                out_buf[body_start : body_start + body_len] = body
                current_offset += total_pkt_len

            if current_offset > 0 and self.running:
                try:
                    sock.sendall(memoryview(out_buf)[:current_offset])
                    metrics_registry.metrics.inc(
                        "ofps.network.bytes_sent_total", current_offset
                    )
                    metrics_registry.metrics.inc(
                        "ofps.network.packets_sent_total", len(tasks)
                    )
                except OSError:
                    self.close()
                    break
                except Exception:
                    logger.exception("Send loop error: %s", self.address)
                    self.close()
                    break

    def _unregister(self):
        # VerifyLoginToken may call close() while already holding lock_session;
        # registry removal therefore belongs to the worker's finalizer.
        from server.scene_data import _session_list, lock_session

        with lock_session:
            _session_list[:] = [session for session in _session_list if session is not self]

    def close(self):
        with self._close_lock:
            if not self.running:
                self.closed.set()
                return
            self.running = False
            metrics_registry.metrics.inc("ofps.sessions.closed_total")
            self._send_event.set()
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.socket.close()
            except OSError:
                pass
            with self._send_lock:
                if self._send_queue:
                    metrics_registry.metrics.inc(
                        "ofps.network.send_queue_tasks", -len(self._send_queue)
                    )
                    metrics_registry.metrics.inc(
                        "ofps.network.send_queue_bytes", -self._send_queued_bytes
                    )
                if self._bulk_send_queue:
                    metrics_registry.metrics.inc(
                        "ofps.network.bulk_send_queue_tasks", -len(self._bulk_send_queue)
                    )
                    metrics_registry.metrics.inc(
                        "ofps.network.bulk_send_queue_bytes", -self._bulk_send_queued_bytes
                    )
                    metrics_registry.metrics.inc(
                        "ofps.network.send_queue_tasks", -len(self._bulk_send_queue)
                    )
                    metrics_registry.metrics.inc(
                        "ofps.network.send_queue_bytes", -self._bulk_send_queued_bytes
                    )
                self._send_queue.clear()
                self._bulk_send_queue.clear()
                self._send_queued_bytes = 0
                self._bulk_send_queued_bytes = 0
            self.closed.set()

    def wait_closed(self, timeout=None):
        return self.closed.wait(timeout)
