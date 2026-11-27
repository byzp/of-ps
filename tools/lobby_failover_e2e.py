"""Headless process-crash lobby failover acceptance test."""

import argparse
import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from lobby_e2e import Bot
from proto.net_pb2 import ChatMsgNotice, PlayerSceneSyncDataNotice, PopEmojiNotice
from network.msg_id import MsgId
from server import lobby_state


def free_port():
    with socket.socket() as sock:
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


def start_server(python, directory, host_id, game_port, http_port, log_path):
    code = r'''
import os
import sys
sys.path.insert(0, sys.argv[1])
from config import Config
Config.DB_PATH = sys.argv[2]
Config.LOBBY_STATE_PATH = sys.argv[3]
Config.LOBBY_HOST_ID = sys.argv[4]
Config.GAME_SERVER_IP = "127.0.0.1"
Config.GAME_SERVER_PORT = int(sys.argv[5])
Config.GAME_SERVER_GADGET_IP = Config.GAME_SERVER_IP
Config.GAME_SERVER_GADGET_PORT = Config.GAME_SERVER_PORT
Config.HTTP_HOST = "127.0.0.1"
Config.HTTP_PORT = int(sys.argv[6])
Config.RES_URL = "http://127.0.0.1:%s/Resources" % Config.HTTP_PORT
Config.SS_SERVER_URL = "http://127.0.0.1:%s" % Config.HTTP_PORT
Config.PAY_URL = "http://127.0.0.1:%s" % Config.HTTP_PORT
Config.PHOTO_SHARE_CDN_URL = "http://127.0.0.1:%s" % Config.HTTP_PORT
Config.ALLOW_LOCAL_TOKEN = True
Config.LOCAL_TOKEN_UIDS = (1000000, 1000001)
Config.LOBBY_LEASE_SECONDS = 0.5
Config.LOBBY_SNAPSHOT_INTERVAL_SEC = 0.1
import main
main.main()
'''
    log = open(log_path, "wb")
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    process = subprocess.Popen(
        [
            python,
            "-c",
            code,
            str(REPO_ROOT),
            str(directory / "player.db"),
            str(directory / "lobby-state.json"),
            host_id,
            str(game_port),
            str(http_port),
        ],
        cwd=REPO_ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        **kwargs,
    )
    log.close()
    return process


def wait_for_snapshot(path, player_ids, previous_epoch, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = lobby_state.load_lobby_state(path)
        if (
            state is not None
            and state["epoch"] > previous_epoch
            and all(str(player_id) in state["projections"] for player_id in player_ids)
        ):
            return state
        time.sleep(0.05)
    raise TimeoutError("periodic lobby snapshot did not contain both players")


def exercise_lobby(port):
    first = Bot(1000000, "127.0.0.1", port).start()
    second = Bot(1000001, "127.0.0.1", port).start()
    try:
        for index in range(10):
            first.send_position(index * 2, 0)
            second.send_position(100 + index * 2, 0)
            time.sleep(0.03)

        first_seen_second = False
        second_seen_first = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not (
            first_seen_second and second_seen_first
        ):
            for bot, target_id, flag in (
                (first, second.player_id, "first"),
                (second, first.player_id, "second"),
            ):
                try:
                    msg_id, body = bot.messages.get_nowait()
                except queue.Empty:
                    continue
                if msg_id == MsgId.PlayerSceneSyncDataNotice:
                    notice = PlayerSceneSyncDataNotice.FromString(body)
                    if any(item.player_id == target_id for item in notice.data):
                        if flag == "first":
                            first_seen_second = True
                        else:
                            second_seen_first = True
            time.sleep(0.01)

        first.send_chat("failover-chat")
        chat_ok = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                msg_id, body = second.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if msg_id == MsgId.ChatMsgNotice:
                if ChatMsgNotice.FromString(body).msg.text == "failover-chat":
                    chat_ok = True
                    break

        first.send_emoji(1)
        emoji_ok = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                msg_id, body = second.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if msg_id == MsgId.PopEmojiNotice:
                if PopEmojiNotice.FromString(body).from_player_id == first.player_id:
                    emoji_ok = True
                    break

        return {
            "position_visible_both_directions": first_seen_second and second_seen_first,
            "chat_broadcast": chat_ok,
            "emoji_broadcast": emoji_ok,
            "errors": first.errors + second.errors,
        }
    finally:
        first.close()
        second.close()


def run(python, directory):
    game_port = free_port()
    http_port = free_port()
    state_path = directory / "lobby-state.json"
    result = {
        "passed": False,
        "checks": {},
        "game_port": game_port,
        "http_port": http_port,
        "errors": [],
    }
    processes = []
    try:
        first_host = start_server(
            python, directory, "host-a", game_port, http_port, directory / "host-a.log"
        )
        processes.append(first_host)
        wait_for_port(game_port, first_host)
        first = Bot(1000000, "127.0.0.1", game_port).start()
        second = Bot(1000001, "127.0.0.1", game_port).start()
        try:
            first.send_position(1, 2, 3)
            second.send_position(4, 5, 6)
            crashed_state = wait_for_snapshot(
                state_path, (first.player_id, second.player_id), previous_epoch=0
            )
            result["checks"]["periodic_snapshot_before_crash"] = True
            result["crashed_epoch"] = crashed_state["epoch"]
        finally:
            first.close()
            second.close()

        first_host.kill()
        first_host.wait(timeout=5.0)
        result["checks"]["host_process_killed"] = True
        promoted = lobby_state.prepare_lobby_failover(
            state_path, "host-b", expected_epoch=crashed_state["epoch"]
        )
        result["checks"]["failover_epoch_advanced"] = promoted["epoch"] == (
            crashed_state["epoch"] + 1
        )

        second_host = start_server(
            python, directory, "host-b", game_port, http_port, directory / "host-b.log"
        )
        processes.append(second_host)
        wait_for_port(game_port, second_host)
        restored = wait_for_snapshot(
            state_path,
            (1000000, 1000001),
            previous_epoch=promoted["epoch"],
        )
        result["checks"]["snapshot_restored_on_new_host"] = (
            restored["host_id"] == "host-b"
            and restored["epoch"] == promoted["epoch"] + 1
        )
        result["restored_epoch"] = restored["epoch"]

        interaction = exercise_lobby(game_port)
        result["checks"].update(
            {
                key: value
                for key, value in interaction.items()
                if key != "errors"
            }
        )
        result["errors"].extend(interaction["errors"])
        result["passed"] = all(result["checks"].values()) and not result["errors"]
        return result
    except Exception as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
        return result
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runtime = Path(r"C:\OverFieldLab\runtime\ofps-failover-e2e")
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=runtime) as temporary:
        directory = Path(temporary)
        result = run(args.python, directory)
        if not result["passed"]:
            result["server_logs"] = {}
            for name in ("host-a.log", "host-b.log"):
                path = directory / name
                if path.exists():
                    result["server_logs"][name] = path.read_text(
                        encoding="utf-8", errors="replace"
                    )[-4000:]
        text = json.dumps(result, ensure_ascii=False, indent=2)
        print(text)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        if not result["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
