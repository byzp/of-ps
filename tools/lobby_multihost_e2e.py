"""Headless two-server, two-client multiplayer acceptance test."""

import argparse
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from lobby_e2e import Bot
from network.msg_id import MsgId
from network.remote_link import REMOTE_PLAYER_ID_BASE
from proto.net_pb2 import (
    ChatMsgNotice,
    PlayerSceneSyncDataNotice,
    PopEmojiNotice,
    SceneActionType,
    SceneDataNotice,
    ServerSceneSyncDataNotice,
)


def free_tcp_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port, process, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"port {port} did not open")


def wait_for_listening(log_path, process, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited with code {process.returncode}")
        if log_path.exists() and "Listening on" in log_path.read_text(
            encoding="utf-8", errors="replace"
        ):
            return
        time.sleep(0.05)
    raise TimeoutError("KCP listener did not start")


def wait_for_link(log_path, process, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited with code {process.returncode}")
        if log_path.exists() and "Server connected:" in log_path.read_text(
            encoding="utf-8", errors="replace"
        ):
            return
        time.sleep(0.05)
    raise TimeoutError("KCP link did not connect")


def start_server(python, directory, host_id, link_port, peer_link_port, log_path):
    game_port = free_tcp_port()
    http_port = free_tcp_port()
    code = r'''
import sys
sys.path.insert(0, sys.argv[1])
from config import Config
Config.DB_PATH = sys.argv[2]
Config.LOBBY_STATE_PATH = None
Config.LOBBY_HOST_ID = sys.argv[3]
Config.GAME_SERVER_IP = "127.0.0.1"
Config.GAME_SERVER_PORT = int(sys.argv[4])
Config.GAME_SERVER_GADGET_IP = Config.GAME_SERVER_IP
Config.GAME_SERVER_GADGET_PORT = Config.GAME_SERVER_PORT
Config.HTTP_HOST = "127.0.0.1"
Config.HTTP_PORT = int(sys.argv[5])
Config.RES_URL = "http://127.0.0.1:%s/Resources" % Config.HTTP_PORT
Config.SS_SERVER_URL = "http://127.0.0.1:%s" % Config.HTTP_PORT
Config.PAY_URL = "http://127.0.0.1:%s" % Config.HTTP_PORT
Config.PHOTO_SHARE_CDN_URL = "http://127.0.0.1:%s" % Config.HTTP_PORT
Config.ALLOW_LOCAL_TOKEN = True
Config.LOCAL_TOKEN_UIDS = (1000000, 1000001)
Config.METRICS_LOG_INTERVAL_SEC = 3600.0
Config.LINK_OTHER_SERVER = True
Config.SERVER_NAME = sys.argv[3]
Config.LINK_LISTEN = ("127.0.0.1", int(sys.argv[6]))
Config.SELF_ADDR = Config.LINK_LISTEN
Config.SELF_ADDR_IS_PUBLIC = True
Config.LINK_POOL = [] if int(sys.argv[7]) == 0 else [("127.0.0.1", int(sys.argv[7]))]
Config.LINK_POOL_CACHE = sys.argv[8]
import main
main.main()
'''
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    with open(log_path, "wb") as log:
        process = subprocess.Popen(
            [
                python,
                "-c",
                code,
                str(REPO_ROOT),
                str(directory / f"{host_id}.db"),
                host_id,
                str(game_port),
                str(http_port),
                str(link_port),
                str(peer_link_port),
                str(directory / f"{host_id}.link.json"),
            ],
            cwd=REPO_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
    return process, game_port, link_port


def wait_for_remote_enter(bot, timeout=8.0):
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        try:
            msg_id, body = bot.next_message(timeout=0.1)
        except queue.Empty:
            continue
        if msg_id != MsgId.ServerSceneSyncDataNotice:
            continue
        notice = ServerSceneSyncDataNotice.FromString(body)
        seen.extend(item.player_id for item in notice.data)
        for item in notice.data:
            if item.player_id < REMOTE_PLAYER_ID_BASE:
                continue
            if any(
                action.action_type == SceneActionType.SceneActionType_ENTER
                for action in item.server_data
            ):
                return item.player_id
    raise TimeoutError(f"remote ENTER was not received; seen={seen[-20:]}")


def wait_for_remote_roster(bot, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg_id, body = bot.next_message(timeout=0.1)
        except queue.Empty:
            continue
        if msg_id != MsgId.SceneDataNotice:
            continue
        notice = SceneDataNotice.FromString(body)
        for player in notice.data.players:
            if player.player_id >= REMOTE_PLAYER_ID_BASE:
                return player.player_id
    raise TimeoutError("remote player was not in the initial scene roster")


def wait_for_remote_position(bot, player_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg_id, body = bot.next_message(timeout=0.1)
        except queue.Empty:
            continue
        if msg_id == MsgId.PlayerSceneSyncDataNotice:
            notice = PlayerSceneSyncDataNotice.FromString(body)
            if any(item.player_id == player_id for item in notice.data):
                return True
    return False


def wait_for_remote_chat(bot, player_id, text, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg_id, body = bot.next_message(timeout=0.1)
        except queue.Empty:
            continue
        if msg_id == MsgId.ChatMsgNotice:
            notice = ChatMsgNotice.FromString(body)
            if notice.msg.player_id == player_id and notice.msg.text == text:
                return True
    return False


def wait_for_remote_emoji(bot, player_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg_id, body = bot.next_message(timeout=0.1)
        except queue.Empty:
            continue
        if msg_id == MsgId.PopEmojiNotice:
            notice = PopEmojiNotice.FromString(body)
            if notice.from_player_id == player_id:
                return True
    return False


def wait_for_remote_leave(bot, player_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg_id, body = bot.next_message(timeout=0.1)
        except queue.Empty:
            continue
        if msg_id != MsgId.ServerSceneSyncDataNotice:
            continue
        notice = ServerSceneSyncDataNotice.FromString(body)
        for item in notice.data:
            if item.player_id != player_id:
                continue
            if any(
                action.action_type == SceneActionType.SceneActionType_LEAVE
                for action in item.server_data
            ):
                return True
    return False


def cleanup_directory(path):
    for _ in range(40):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            time.sleep(0.05)
        except FileNotFoundError:
            return
    raise PermissionError(f"unable to remove test directory {path}")


def run(python, directory):
    result = {"passed": False, "checks": {}, "errors": []}
    processes = []
    clients = []
    try:
        from network import remote_link

        if remote_link.KCP_IMPORT_FAILED:
            raise RuntimeError(
                "KCP extension is unavailable; build utils/kcp/setup.py first"
            )
        link_a = free_udp_port()
        link_b = free_udp_port()
        server_a, port_a, _ = start_server(
            python, directory, "host-a", link_a, 0, directory / "host-a.log"
        )
        processes.append(server_a)
        wait_for_port(port_a, server_a)
        wait_for_listening(directory / "host-a.log", server_a)
        server_b, port_b, _ = start_server(
            python, directory, "host-b", link_b, link_a, directory / "host-b.log"
        )
        processes.append(server_b)
        wait_for_port(port_b, server_b)
        wait_for_listening(directory / "host-b.log", server_b)
        wait_for_link(directory / "host-b.log", server_b)
        result["checks"]["kcp_link_connected"] = True

        first = Bot(1000000, "127.0.0.1", port_a)
        clients.append(first)
        first.start()
        second = Bot(1000001, "127.0.0.1", port_b)
        clients.append(second)
        second.start()

        remote_second = wait_for_remote_enter(first)
        remote_first = wait_for_remote_roster(second)
        result["checks"]["remote_enter_and_initial_roster"] = True
        result["remote_player_ids"] = [remote_first, remote_second]

        for index in range(10):
            first.send_position(10 + index * 2, 20)
            second.send_position(100 + index * 2, 200)
            time.sleep(0.03)
        result["checks"]["remote_position_to_first"] = wait_for_remote_position(
            first, remote_second
        )
        result["checks"]["remote_position_to_second"] = wait_for_remote_position(
            second, remote_first
        )

        first.send_chat("multi-host-chat")
        result["checks"]["cross_host_chat"] = wait_for_remote_chat(
            second, remote_first, "multi-host-chat"
        )

        first.send_emoji(1)
        result["checks"]["cross_host_emoji"] = wait_for_remote_emoji(
            second, remote_first
        )

        second.close()
        clients.remove(second)
        result["checks"]["remote_leave_visible"] = wait_for_remote_leave(
            first, remote_second, timeout=15.0
        )
        result["errors"] = first.errors
        result["passed"] = all(result["checks"].values()) and not result["errors"]
        return result
    except Exception as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
        for client in clients:
            result["errors"].extend(client.errors)
        return result
    finally:
        for client in clients:
            client.close()
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5.0)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runtime = Path(r"C:\OverFieldLab\runtime\ofps-multihost-e2e")
    runtime.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=runtime))
    try:
        result = run(args.python, directory)
        if not result["passed"]:
            for name in ("host-a.log", "host-b.log"):
                path = directory / name
                if path.exists():
                    shutil.copyfile(path, runtime / f"last-{name}")
            result["server_logs"] = {}
            for name in ("host-a.log", "host-b.log"):
                path = directory / name
                if path.exists():
                    result["server_logs"][name] = path.read_text(
                        encoding="utf-8", errors="replace"
                    )[-12000:]
        text = json.dumps(result, ensure_ascii=False, indent=2)
        print(text)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        if not result["passed"]:
            raise SystemExit(1)
    finally:
        cleanup_directory(directory)


if __name__ == "__main__":
    main()
