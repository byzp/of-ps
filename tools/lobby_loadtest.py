"""In-process real-TCP lobby load test for of-ps.

Starts the actual GameServer, notice_sync, framing, session queues and shared
projection store. Authentication and persistence are replaced with bounded
fakes so the benchmark needs no game database or client assets.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
import math
import multiprocessing
import os
import queue
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cramjam import snappy

from config import Config
from handlers.PlayerPing import Handler as PingHandler
from handlers.PlayerSceneRecord import Handler as SceneRecordHandler
from network.game_server import GameServer
from network.game_session import GameSession
from network.msg_id import MsgId
from network.packet_factory import PacketFactory
from proto.net_pb2 import (
    CharacterRecorderData,
    PacketHead,
    PlayerLoginReq,
    PlayerLoginRsp,
    PlayerPingReq,
    PlayerRecorderData,
    PlayerSceneRecordReq,
    PlayerSceneSyncDataNotice,
    StatusCode,
    Vector3,
    VerifyLoginTokenReq,
    VerifyLoginTokenRsp,
)
from server import notice_sync, shared_projection
from server.scene_data import (
    _rec_list,
    _scene,
    _session_list,
    clear_scene_snapshots,
    lock_session,
)
from utils.metrics import metrics

HDR = struct.Struct(">H")


def frame(msg_id, body=b"", packet_id=1):
    head = PacketHead(msg_id=msg_id, packet_id=packet_id, body_len=len(body))
    payload = head.SerializeToString()
    return HDR.pack(len(payload)) + payload + body


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("closed by peer")
        data.extend(chunk)
    return bytes(data)


def recv_packet(sock):
    header_len = HDR.unpack(recv_exact(sock, 2))[0]
    head = PacketHead()
    head.ParseFromString(recv_exact(sock, header_len))
    body = recv_exact(sock, head.body_len)
    if head.flag == 1:
        body = bytes(snappy.decompress_raw(body))
    return head, body


def reserve_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def pct(values, p):
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round((len(values) - 1) * p)))]


def peak_rss_bytes():
    if os.name != "nt":
        try:
            import resource

            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        except Exception:
            return None

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    try:
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            return int(counters.PeakWorkingSetSize)
    except Exception:
        pass
    return None


class VerifyHandler:
    _next_id = 1000000
    _lock = threading.Lock()

    def handle(self, session, data, packet_id):
        session.verified = True
        with self._lock:
            session.player_id = self._next_id
            self._next_id += 1
        session.player_name = f"bot-{session.player_id}"
        session.send(
            MsgId.VerifyLoginTokenRsp,
            VerifyLoginTokenRsp(status=StatusCode.StatusCode_OK),
            packet_id,
        )


class LoginHandler:
    def handle(self, session, data, packet_id):
        session.logged_in = True
        session.send(
            MsgId.PlayerLoginRsp,
            PlayerLoginRsp(status=StatusCode.StatusCode_OK),
            packet_id,
        )


class Bot(threading.Thread):
    def __init__(
        self,
        index,
        total,
        host,
        port,
        seconds,
        rate,
        spread,
        move_radius,
        ping_interval,
        barrier,
        results,
        result_lock,
    ):
        super().__init__(daemon=True)
        self.index = index
        self.total = total
        self.host = host
        self.port = port
        self.seconds = seconds
        self.rate = rate
        self.spread = spread
        self.move_radius = move_radius
        self.ping_interval = ping_interval
        self.barrier = barrier
        self.results = results
        self.result_lock = result_lock
        self.packet_id = index * 10_000_000 + 1
        self.stop = threading.Event()
        self.ping_responses = queue.Queue()
        self.rtts = []
        self.sent_positions = 0
        self.received_packets = 0
        self.received_bytes = 0
        self.position_notices = 0
        self.position_players = 0
        self.errors = []

    def next_packet_id(self):
        value = self.packet_id
        self.packet_id += 1
        return value

    def record_error(self, error):
        with self.result_lock:
            self.errors.append(f"{type(error).__name__}: {error}")

    def to_dict(self):
        return {
            "index": self.index,
            "rtts": self.rtts,
            "sent_positions": self.sent_positions,
            "received_packets": self.received_packets,
            "received_bytes": self.received_bytes,
            "position_notices": self.position_notices,
            "position_players": self.position_players,
            "errors": self.errors,
        }

    def initial_position(self, total):
        angle = self.index * 2.399963229728653
        radius = self.spread * math.sqrt((self.index + 1) / max(1, total))
        return radius * math.cos(angle), radius * math.sin(angle)

    def position_packet(self, x, y, z=0):
        data = PlayerRecorderData()
        record = data.char_recorder_data_lst.add()
        record.char_id = 1
        record.pos.CopyFrom(Vector3(x=int(x), y=int(y), z=int(z)))
        record.rot.CopyFrom(Vector3(x=0, y=0, z=0))
        return frame(
            MsgId.PlayerSceneRecordReq,
            PlayerSceneRecordReq(data=data).SerializeToString(),
            self.next_packet_id(),
        )

    def reader(self, sock):
        sock.settimeout(0.2)
        try:
            while not self.stop.is_set():
                try:
                    head, body = recv_packet(sock)
                except socket.timeout:
                    continue
                self.received_packets += 1
                self.received_bytes += 2 + len(head.SerializeToString()) + len(body)
                if head.msg_id == MsgId.PlayerPingRsp:
                    self.ping_responses.put((head.packet_id, time.perf_counter()))
                elif head.msg_id == MsgId.PlayerSceneSyncDataNotice:
                    self.position_notices += 1
                    notice = PlayerSceneSyncDataNotice.FromString(body)
                    self.position_players += len(notice.data)
        except Exception as error:
            if not self.stop.is_set():
                self.record_error(error)

    def run(self):
        sock = None
        reader = None
        try:
            sock = socket.create_connection((self.host, self.port), timeout=5.0)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(5.0)

            packet_id = self.next_packet_id()
            sock.sendall(
                frame(
                    MsgId.VerifyLoginTokenReq,
                    VerifyLoginTokenReq().SerializeToString(),
                    packet_id,
                )
            )
            head, _ = recv_packet(sock)
            if head.msg_id != MsgId.VerifyLoginTokenRsp:
                raise RuntimeError("verify login failed")

            packet_id = self.next_packet_id()
            sock.sendall(
                frame(
                    MsgId.PlayerLoginReq,
                    PlayerLoginReq().SerializeToString(),
                    packet_id,
                )
            )
            head, _ = recv_packet(sock)
            if head.msg_id != MsgId.PlayerLoginRsp:
                raise RuntimeError("player login failed")

            reader = threading.Thread(target=self.reader, args=(sock,), daemon=True)
            reader.start()
            self.barrier.wait(timeout=15.0)

            base_x, base_y = self.initial_position(self.total)
            started = time.perf_counter()
            next_position = started
            next_ping = started
            ping_waiting = None
            ping_sent_at = None
            while time.perf_counter() - started < self.seconds:
                now = time.perf_counter()
                if now >= next_position:
                    phase = (now - started) * 0.7
                    x = base_x + self.move_radius * math.cos(phase + self.index)
                    y = base_y + self.move_radius * math.sin(phase + self.index)
                    sock.sendall(self.position_packet(x, y))
                    self.sent_positions += 1
                    next_position += 1.0 / self.rate

                if now >= next_ping:
                    packet_id = self.next_packet_id()
                    request = PlayerPingReq(client_time_ms=int(time.time() * 1000))
                    ping_sent_at = time.perf_counter()
                    sock.sendall(
                        frame(
                            MsgId.PlayerPingReq,
                            request.SerializeToString(),
                            packet_id,
                        )
                    )
                    ping_waiting = packet_id
                    next_ping += self.ping_interval

                if ping_waiting is not None:
                    try:
                        response_id, response_at = self.ping_responses.get_nowait()
                    except queue.Empty:
                        pass
                    else:
                        if response_id == ping_waiting:
                            self.rtts.append((response_at - ping_sent_at) * 1000.0)
                            ping_waiting = None
                time.sleep(0.0005)
        except Exception as error:
            self.record_error(error)
        finally:
            self.stop.set()
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            if reader is not None:
                reader.join(timeout=1.0)


def bot_process_entry(
    host,
    port,
    indices,
    total,
    seconds,
    rate,
    spread,
    move_radius,
    ping_interval,
    barrier,
    result_queue,
):
    result_lock = threading.Lock()
    bots = [
        Bot(
            index=index,
            total=total,
            host=host,
            port=port,
            seconds=seconds,
            rate=rate,
            spread=spread,
            move_radius=move_radius,
            ping_interval=ping_interval,
            barrier=barrier,
            results=[],
            result_lock=result_lock,
        )
        for index in indices
    ]
    for bot in bots:
        bot.start()
    deadline = time.monotonic() + seconds + 20.0
    for bot in bots:
        bot.join(timeout=max(0.0, deadline - time.monotonic()))
    result_queue.put([bot.to_dict() for bot in bots])


def install_handlers():
    executor = ThreadPoolExecutor(
        max_workers=Config.PACKET_POOL_MAX_WORKERS,
        thread_name_prefix="lobby-loadtest-packet",
    )

    def initialize(cls, package_name):
        cls.shutdown()
        VerifyHandler._next_id = 1000000
        cls._handlers = {
            MsgId.VerifyLoginTokenReq: VerifyHandler(),
            MsgId.PlayerLoginReq: LoginHandler(),
            MsgId.PlayerSceneRecordReq: SceneRecordHandler(),
            MsgId.PlayerPingReq: PingHandler(),
        }
        cls._executor = executor
        cls._accepting = True

    return initialize


def run(args):
    port = args.port or reserve_port()
    metrics.reset()
    shared_projection.store.clear()
    notice_sync._last_global_position_sync.clear()
    with lock_session:
        _session_list.clear()
    _scene.clear()
    clear_scene_snapshots()
    _rec_list.clear()

    cpu_started = time.process_time()
    wall_started = time.perf_counter()
    server = None
    thread = None

    with patch.object(Config, "GAME_SERVER_IP", "127.0.0.1"), patch.object(
        Config, "GAME_SERVER_PORT", port
    ), patch.object(
        Config, "SESSION_POOL_MAX_WORKERS", max(16, args.clients * 2)
    ), patch.object(
        Config, "PACKET_POOL_MAX_WORKERS", max(4, min(32, args.clients))
    ), patch.object(
        Config, "SCENE_AOI_RADIUS", args.aoi_radius
    ), patch.object(
        Config, "SCENE_GLOBAL_SYNC_INTERVAL", args.global_interval
    ), patch.object(
        Config, "METRICS_LOG_INTERVAL_SEC", 3600.0
    ), patch.object(
        PacketFactory, "initialize_handlers", classmethod(install_handlers())
    ), patch.object(
        PacketFactory,
        "MAX_PENDING_PACKETS",
        args.max_pending or max(256, args.clients * 32),
    ), patch.object(
        PacketFactory, "MAX_PENDING_BYTES", 256 * 1024 * 1024
    ), patch.object(
        notice_sync, "_save_local_session"
    ), patch.object(
        notice_sync.mail_rewards, "recover_drops"
    ), patch(
        "handlers.PlayerSceneRecord.save_session_location"
    ):
        server = GameServer()
        server.ACCEPT_TIMEOUT = 0.02
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        if not server.wait_started(5.0):
            raise RuntimeError(f"server failed to start: {server.startup_error}")

        try:
            if args.processes <= 1:
                barrier = threading.Barrier(args.clients)
                result_lock = threading.Lock()
                bots = [
                    Bot(
                        index=index,
                        total=args.clients,
                        host="127.0.0.1",
                        port=port,
                        seconds=args.seconds,
                        rate=args.rate,
                        spread=args.spread,
                        move_radius=args.move_radius,
                        ping_interval=args.ping_interval,
                        barrier=barrier,
                        results=[],
                        result_lock=result_lock,
                    )
                    for index in range(args.clients)
                ]
                for bot in bots:
                    bot.start()
                deadline = time.monotonic() + args.seconds + 20.0
                for bot in bots:
                    bot.join(timeout=max(0.0, deadline - time.monotonic()))
                if any(bot.is_alive() for bot in bots):
                    raise RuntimeError("one or more lobby bots did not stop")
                bot_dicts = [bot.to_dict() for bot in bots]
            else:
                ctx = multiprocessing.get_context("spawn")
                barrier = ctx.Barrier(args.clients)
                result_queue = ctx.Queue()
                groups = [
                    list(range(index, args.clients, args.processes))
                    for index in range(args.processes)
                ]
                processes = [
                    ctx.Process(
                        target=bot_process_entry,
                        args=(
                            "127.0.0.1",
                            port,
                            group,
                            args.clients,
                            args.seconds,
                            args.rate,
                            args.spread,
                            args.move_radius,
                            args.ping_interval,
                            barrier,
                            result_queue,
                        ),
                    )
                    for group in groups
                    if group
                ]
                try:
                    for process in processes:
                        process.start()
                    deadline = time.monotonic() + args.seconds + 30.0
                    bot_dicts = []
                    try:
                        for _ in processes:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                raise queue.Empty
                            bot_dicts.extend(result_queue.get(timeout=remaining))
                    except queue.Empty as error:
                        alive = [
                            process.pid
                            for process in processes
                            if process.is_alive()
                        ]
                        raise RuntimeError(
                            "lobby bot processes did not report results: "
                            f"alive={alive}, exitcodes={[p.exitcode for p in processes]}"
                        ) from error
                    for process in processes:
                        process.join(timeout=max(0.0, deadline - time.monotonic()))
                    if any(process.is_alive() for process in processes):
                        alive = [
                            process.pid
                            for process in processes
                            if process.is_alive()
                        ]
                        exitcodes = [process.exitcode for process in processes]
                        raise RuntimeError(
                            "one or more lobby bot processes did not stop: "
                            f"alive={alive}, exitcodes={exitcodes}"
                        )
                finally:
                    for process in processes:
                        if process.is_alive():
                            process.terminate()
                            process.join(timeout=2.0)
            bots = [SimpleNamespace(**item) for item in bot_dicts]
            projection_snapshot = shared_projection.store.snapshot()
        finally:
            server.stop()
            thread.join(timeout=5.0)
            if thread.is_alive():
                raise RuntimeError("game server thread did not stop")

        snapshot = metrics.snapshot()

    cpu_seconds = time.process_time() - cpu_started
    wall_seconds = time.perf_counter() - wall_started
    all_rtts = [value for bot in bots for value in bot.rtts]
    errors = [error for bot in bots for error in bot.errors]
    counters = snapshot["counters"]
    timers = snapshot["timers"]

    result = {
        "clients": args.clients,
        "processes": args.processes,
        "seconds": args.seconds,
        "position_rate_hz": args.rate,
        "aoi_radius": args.aoi_radius,
        "global_interval_sec": args.global_interval,
        "spread": args.spread,
        "projection_active": len(projection_snapshot),
        "projection_sample": [
            projection_snapshot[key]
            for key in sorted(projection_snapshot)[:5]
        ],
        "login_errors": errors,
        "positions_sent": sum(bot.sent_positions for bot in bots),
        "packets_received_by_clients": sum(
            bot.received_packets for bot in bots
        ),
        "bytes_received_by_clients": sum(bot.received_bytes for bot in bots),
        "position_notices_received": sum(
            bot.position_notices for bot in bots
        ),
        "ping_rtt_ms": {
            "count": len(all_rtts),
            "p50": pct(all_rtts, 0.50),
            "p95": pct(all_rtts, 0.95),
            "p99": pct(all_rtts, 0.99),
            "max": max(all_rtts) if all_rtts else None,
        },
        "server": {
            "cpu_seconds": cpu_seconds,
            "wall_seconds": wall_seconds,
            "peak_rss_bytes": peak_rss_bytes(),
            "bytes_sent": counters.get("ofps.network.bytes_sent_total", 0),
            "packets_sent": counters.get("ofps.network.packets_sent_total", 0),
            "sessions_created": counters.get("ofps.sessions.created_total", 0),
            "sessions_closed": counters.get("ofps.sessions.closed_total", 0),
            "notice_cycles": counters.get("ofps.notice.cycles_total", 0),
            "notice_over_budget": counters.get(
                "ofps.notice.over_budget_total", 0
            ),
            "notice_cycle_avg_ms": timers.get(
                "ofps.notice.cycle_duration_seconds", {}
            ).get("avg_seconds", 0.0)
            * 1000.0,
            "notice_cycle_max_ms": timers.get(
                "ofps.notice.cycle_duration_seconds", {}
            ).get("max_seconds", 0.0)
            * 1000.0,
            "position_global_sends": counters.get(
                "ofps.notice.position_global_sends", 0
            ),
            "position_aoi_sends": counters.get(
                "ofps.notice.position_aoi_sends", 0
            ),
            "position_players_sent": counters.get(
                "ofps.notice.position_players_sent", 0
            ),
        },
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, default=20)
    parser.add_argument("--processes", type=int, default=1)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--rate", type=float, default=20.0, help="position Hz per bot")
    parser.add_argument("--aoi-radius", type=float, default=80.0)
    parser.add_argument("--global-interval", type=float, default=0.5)
    parser.add_argument("--spread", type=float, default=100.0)
    parser.add_argument("--move-radius", type=float, default=5.0)
    parser.add_argument("--ping-interval", type=float, default=1.0)
    parser.add_argument("--max-pending", type=int, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    if args.clients < 1 or args.processes < 1 or args.seconds <= 0 or args.rate <= 0:
        parser.error("clients, processes, seconds and rate must be positive")
    if args.aoi_radius < 0 or args.global_interval <= 0:
        parser.error("aoi-radius must be non-negative and global-interval positive")

    result = run(args)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    if result["login_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
