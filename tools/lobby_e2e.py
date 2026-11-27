"""Headless two-client lobby E2E using the real of-ps TCP protocol."""

import argparse
import json
import queue
import socket
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cramjam import snappy

from network.msg_id import MsgId
from proto.net_pb2 import (
    CharacterRecorderData,
    ChatChannelType,
    PacketHead,
    PlayerLoginReq,
    PlayerMainDataReq,
    PlayerRecorderData,
    PlayerSceneRecordReq,
    PopEmojiReq,
    SendChatMsgReq,
    StatusCode,
    Vector3,
    VerifyLoginTokenReq,
)

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


class Bot:
    def __init__(self, uid, host, port):
        self.uid = uid
        self.host = host
        self.port = port
        self.player_id = uid
        self.packet_id = uid
        self.sock = None
        self.reader = None
        self.stop = threading.Event()
        self.messages = queue.Queue()
        self.errors = []

    def next_id(self):
        self.packet_id += 1
        return self.packet_id

    def start(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=5.0)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.settimeout(None)
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()

        request = VerifyLoginTokenReq(
            sdk_uid=str(self.uid),
            login_token="local-session",
            account_type=9999,
            device_uuid=f"headless-{self.uid}",
        )
        self.sock.sendall(
            frame(MsgId.VerifyLoginTokenReq, request.SerializeToString(), self.next_id())
        )
        msg_id, body = self.wait_for(MsgId.VerifyLoginTokenRsp, timeout=5.0)
        if msg_id != MsgId.VerifyLoginTokenRsp:
            raise RuntimeError("verify login failed")
        from proto.net_pb2 import VerifyLoginTokenRsp

        if VerifyLoginTokenRsp.FromString(body).status != StatusCode.StatusCode_OK:
            raise RuntimeError("verify login rejected")

        self.sock.sendall(
            frame(MsgId.PlayerLoginReq, PlayerLoginReq().SerializeToString(), self.next_id())
        )
        msg_id, body = self.wait_for(MsgId.PlayerLoginRsp, timeout=5.0)
        from proto.net_pb2 import PlayerLoginRsp

        if PlayerLoginRsp.FromString(body).status != StatusCode.StatusCode_OK:
            raise RuntimeError("player login rejected")

        self.sock.sendall(
            frame(MsgId.PlayerMainDataReq, PlayerMainDataReq().SerializeToString(), self.next_id())
        )
        return self

    def _read_loop(self):
        try:
            while not self.stop.is_set():
                head, body = recv_packet(self.sock)
                self.messages.put((head.msg_id, body))
        except Exception as error:
            if not self.stop.is_set():
                self.errors.append(f"{type(error).__name__}: {error}")

    def wait_for(self, msg_id, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                current_id, body = self.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if current_id == msg_id:
                return current_id, body
        raise TimeoutError(f"message {msg_id} not received")

    def send_position(self, x, y, z=0):
        data = PlayerRecorderData()
        record = data.char_recorder_data_lst.add()
        record.char_id = 1
        record.pos.CopyFrom(Vector3(x=int(x), y=int(y), z=int(z)))
        record.rot.CopyFrom(Vector3(x=0, y=0, z=0))
        self.sock.sendall(
            frame(
                MsgId.PlayerSceneRecordReq,
                PlayerSceneRecordReq(data=data).SerializeToString(),
                self.next_id(),
            )
        )

    def send_chat(self, text):
        request = SendChatMsgReq(
            type=ChatChannelType.ChatChannel_Default,
            player_id=self.player_id,
            text=text,
            expression=0,
        )
        self.sock.sendall(
            frame(MsgId.SendChatMsgReq, request.SerializeToString(), self.next_id())
        )

    def send_emoji(self, emoji_id=1):
        self.sock.sendall(
            frame(MsgId.PopEmojiReq, PopEmojiReq(emoji_id=emoji_id).SerializeToString(), self.next_id())
        )

    def close(self):
        self.stop.set()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        if self.reader is not None:
            self.reader.join(timeout=1.0)


def run(host, port):
    bots = []
    result = {"passed": False, "checks": {}, "errors": []}
    try:
        first = Bot(1000000, host, port).start()
        second = Bot(1000001, host, port).start()
        bots = [first, second]

        for index in range(10):
            first.send_position(index * 2, 0)
            second.send_position(100 + index * 2, 0)
            time.sleep(0.05)

        from proto.net_pb2 import PlayerSceneSyncDataNotice

        first_seen_second = False
        second_seen_first = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not (first_seen_second and second_seen_first):
            for bot, target_id, flag_name in (
                (first, second.player_id, "first_seen_second"),
                (second, first.player_id, "second_seen_first"),
            ):
                try:
                    msg_id, body = bot.messages.get_nowait()
                except queue.Empty:
                    continue
                if msg_id == MsgId.PlayerSceneSyncDataNotice:
                    notice = PlayerSceneSyncDataNotice.FromString(body)
                    if any(item.player_id == target_id for item in notice.data):
                        if flag_name == "first_seen_second":
                            first_seen_second = True
                        else:
                            second_seen_first = True
            time.sleep(0.01)

        result["checks"]["position_visible_both_directions"] = first_seen_second and second_seen_first

        chat_text = "headless-lobby-chat"
        first.send_chat(chat_text)
        chat_ok = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                msg_id, body = second.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if msg_id == MsgId.ChatMsgNotice:
                from proto.net_pb2 import ChatMsgNotice

                notice = ChatMsgNotice.FromString(body)
                if notice.msg.text == chat_text:
                    chat_ok = True
                    break
        result["checks"]["chat_broadcast"] = chat_ok

        first.send_emoji(1)
        emoji_ok = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                msg_id, body = second.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            if msg_id == MsgId.PopEmojiNotice:
                from proto.net_pb2 import PopEmojiNotice

                notice = PopEmojiNotice.FromString(body)
                if notice.from_player_id == first.player_id:
                    emoji_ok = True
                    break
        result["checks"]["emoji_broadcast"] = emoji_ok

        result["errors"] = first.errors + second.errors
        result["passed"] = all(result["checks"].values()) and not result["errors"]
        return result
    except Exception as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
        return result
    finally:
        for bot in bots:
            bot.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11033)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.host, args.port)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
