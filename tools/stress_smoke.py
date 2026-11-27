"""Bounded, in-process network lifecycle smoke test.

This starts only the real TCP accept/session/framing code on loopback.  Login
handlers, persistence and notice sync are replaced with local fakes, so no game
database, remote server or long-running background service is required.
"""

import argparse
import contextlib
import json
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config
from network.game_server import GameServer
from network.game_session import GameSession
from network.msg_id import MsgId
from network.packet_factory import PacketFactory
from proto.net_pb2 import PacketHead, PlayerLoginRsp, StatusCode, VerifyLoginTokenRsp
import server.notice_sync as notice_sync
from server.scene_data import _session_list, lock_session


def frame(msg_id, body=b"", packet_id=1, body_len=None):
    head = PacketHead(
        msg_id=msg_id,
        packet_id=packet_id,
        body_len=len(body) if body_len is None else body_len,
    ).SerializeToString()
    return struct.pack(">H", len(head)) + head + body


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection closed before packet completed")
        data.extend(chunk)
    return bytes(data)


def recv_packet(sock):
    head_len = struct.unpack(">H", recv_exact(sock, 2))[0]
    head = PacketHead()
    head.ParseFromString(recv_exact(sock, head_len))
    body = recv_exact(sock, head.body_len)
    return head, body


def reserve_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_local_sessions_to_drain(timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with lock_session:
            if not any(not getattr(item, "remote", False) for item in _session_list):
                return
        time.sleep(0.005)
    raise TimeoutError("local sessions did not drain")


def assert_closed(sock, timeout=1.0):
    sock.settimeout(timeout)
    try:
        return sock.recv(1) == b""
    except (ConnectionResetError, BrokenPipeError):
        return True


def run(cycles, clients, rounds, port=None):
    port = port or reserve_port()
    old_sessions = list(_session_list)
    seen_sessions = []
    login_count = 0
    peak_connections = 0

    def process_packet(msg_id, body, packet_id, session):
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
            seen_sessions.append(session)
            session.send(
                MsgId.PlayerLoginRsp,
                PlayerLoginRsp(status=StatusCode.StatusCode_OK),
                packet_id,
            )
        return True

    try:
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(Config, "GAME_SERVER_IP", "127.0.0.1"))
            stack.enter_context(patch.object(Config, "GAME_SERVER_PORT", port))
            stack.enter_context(patch.object(Config, "SESSION_POOL_MAX_WORKERS", 4))
            stack.enter_context(patch.object(PacketFactory, "initialize_handlers"))
            stack.enter_context(patch.object(PacketFactory, "shutdown"))
            stack.enter_context(patch.object(PacketFactory, "process_packet", side_effect=process_packet))
            stack.enter_context(patch.object(notice_sync, "init", return_value=None))
            stack.enter_context(patch.object(notice_sync, "stop"))
            stack.enter_context(patch.object(GameSession, "AUTH_TIMEOUT", 1.0))
            stack.enter_context(patch.object(GameSession, "PACKET_TIMEOUT", 0.1))
            stack.enter_context(patch.object(GameSession, "_READ_POLL_INTERVAL", 0.02))

            for cycle in range(cycles):
                server = GameServer()
                server.ACCEPT_TIMEOUT = 0.02
                thread = threading.Thread(target=server.start, name=f"stress-game-{cycle}")
                thread.start()
                try:
                    if not server.wait_started(2.0):
                        raise RuntimeError(f"cycle {cycle}: server failed to start")
                    if server.server_socket.getsockname()[1] != port:
                        raise RuntimeError(f"cycle {cycle}: unexpected bound port")

                    for client_index in range(clients):
                        for attempt in range(rounds):
                            packet_id = cycle * 10000 + client_index * 100 + attempt * 2 + 1
                            with socket.create_connection(("127.0.0.1", port), timeout=1.0) as client:
                                client.sendall(frame(MsgId.VerifyLoginTokenReq, packet_id=packet_id))
                                head, body = recv_packet(client)
                                response = VerifyLoginTokenRsp.FromString(body)
                                if head.msg_id != MsgId.VerifyLoginTokenRsp or response.status != StatusCode.StatusCode_OK:
                                    raise RuntimeError(f"cycle {cycle}: verify login failed")
                                client.sendall(frame(MsgId.PlayerLoginReq, packet_id=packet_id + 1))
                                head, body = recv_packet(client)
                                response = PlayerLoginRsp.FromString(body)
                                if head.msg_id != MsgId.PlayerLoginRsp or response.status != StatusCode.StatusCode_OK:
                                    raise RuntimeError(f"cycle {cycle}: player login failed")
                                login_count += 1
                                if (cycle + client_index + attempt) % 2:
                                    client.setsockopt(
                                        socket.SOL_SOCKET,
                                        socket.SO_LINGER,
                                        struct.pack("ii", 1, 0),
                                    )
                            wait_for_local_sessions_to_drain()

                    # Boundary probes: unauthorized packet, oversized declared
                    # body, and a partial frame that trickles into a dead line.
                    probes = (
                        frame(MsgId.PlayerLoginReq),
                        frame(MsgId.PlayerMainDataReq, body_len=GameSession.MAX_WIRE_BODY_BYTES + 1),
                        b"\x00",
                    )
                    for probe in probes:
                        with socket.create_connection(("127.0.0.1", port), timeout=1.0) as client:
                            client.sendall(probe)
                            if not assert_closed(client):
                                raise RuntimeError(f"cycle {cycle}: invalid connection was not closed")
                        wait_for_local_sessions_to_drain()

                    with lock_session:
                        peak_connections = max(peak_connections, len(_session_list))
                finally:
                    server.stop()
                    server.stop()
                    thread.join(2.0)
                if thread.is_alive():
                    raise RuntimeError(f"cycle {cycle}: accept thread leaked")
                if not server.stopped:
                    raise RuntimeError(f"cycle {cycle}: shutdown did not complete")
                with lock_session:
                    if _session_list:
                        raise RuntimeError(f"cycle {cycle}: session registry was not cleared")

        for session in seen_sessions:
            if session.running or session._send_thread.is_alive():
                raise RuntimeError("session sender leaked after shutdown")
        return {
            "cycles": cycles,
            "logins": login_count,
            "port": port,
            "peak_connections": peak_connections,
            "residual_sessions": 0,
        }
    finally:
        for session in list(_session_list):
            try:
                session.close()
            except Exception:
                pass
        with lock_session:
            _session_list[:] = old_sessions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--port", type=int, default=None, help="reuse this loopback TCP port")
    args = parser.parse_args()
    if args.cycles < 1 or args.clients < 1 or args.rounds < 1:
        parser.error("cycles, clients and rounds must be positive")
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    started = time.monotonic()
    try:
        result = run(args.cycles, args.clients, args.rounds, args.port)
    except Exception as error:
        print(f"stress smoke failed: {error}", file=sys.stderr)
        return 1
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
