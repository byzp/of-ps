import socket
import threading
import logging
import json
import time
import uuid
import base64
import os
import traceback
from config import Config
from network.game_session import GameSession, snappy
from google.protobuf.message import Message
import proto.OverField_pb2 as pb
from server.scene_data import (
    get_session,
    up_action,
    up_scene_action,
    up_chat_msg,
    up_recorder,
    _session_list as session_list,
    lock_session,
)

logger = logging.getLogger(__name__)

_remote_servers = {}
_server_ids = {}
_last_heartbeat = {}
_seen_messages = {}
_lock = threading.Lock()
_socket = None
_socket_ready = threading.Event()

_HANDSHAKE_PREFIX = b"of-ps:"
_MSG_TTL = 60
_HEARTBEAT_INTERVAL = 3
_HEARTBEAT_TIMEOUT = 10


def _make_handshake():
    return _HANDSHAKE_PREFIX + Config.SERVER_NAME.encode()


def _parse_handshake(data):
    if data.startswith(_HANDSHAKE_PREFIX):
        try:
            return data[len(_HANDSHAKE_PREFIX) :].decode()
        except:
            pass
    return None


def _trans_player_id(server_name, player_id):
    with _lock:
        if server_name not in _server_ids:
            _server_ids[server_name] = (len(_server_ids) + 1) * 10000
        return _server_ids[server_name] + player_id


def _get_server_name_by_addr(addr):
    with _lock:
        for name, server_addr in _remote_servers.items():
            if server_addr == addr:
                return name
    return None


def _add_server(server_name, addr):
    if server_name == Config.SERVER_NAME:
        return False
    with _lock:
        is_new = server_name not in _remote_servers
        _remote_servers[server_name] = addr
        _last_heartbeat[server_name] = time.time()
        if is_new and server_name not in _server_ids:
            _server_ids[server_name] = (len(_server_ids) + 1) * 10000
    return is_new


def _remove_server(server_name):
    with _lock:
        _remote_servers.pop(server_name, None)
        _last_heartbeat.pop(server_name, None)


def _message_handler(server_name, player_id, scene_id, channel_id, msg_id, payload):
    pid = _trans_player_id(server_name, player_id)
    if msg_id == 1970:
        rsp = pb.SendActionNotice()
        rsp.ParseFromString(payload)
        up_action(pid, rsp.from_player_name, scene_id, channel_id, rsp.action_id)
    elif msg_id == 1208:
        rsp = pb.ServerSceneSyncDataNotice()
        rsp.ParseFromString(payload)
        for data in rsp.data:
            data.player_id = _trans_player_id(server_name, data.player_id)
            for sd in data.server_data:
                if sd.player.player_id:
                    sd.player.player_id = _trans_player_id(
                        server_name, sd.player.player_id
                    )
        up_scene_action(scene_id, channel_id, rsp)
    elif msg_id == 1936:
        rsp = pb.ChatMsgNotice()
        rsp.ParseFromString(payload)
        up_chat_msg(
            rsp.type, pid, rsp.msg.text, rsp.msg.expression, scene_id, channel_id
        )
    elif msg_id == 1206:
        rsp = pb.PlayerSceneSyncDataNotice()
        rsp.ParseFromString(payload)
        for data in rsp.data:
            data.player_id = _trans_player_id(server_name, data.player_id)
            up_recorder(scene_id, channel_id, data.player_id, data.data[0])


def _load_servers():
    if os.path.exists(Config.LINK_POOL_CACHE):
        try:
            with open(Config.LINK_POOL_CACHE, "r") as f:
                return [tuple(addr) for addr in json.load(f)]
        except Exception as e:
            logger.error(f"Failed to load server cache: {e}")
    return []


def _save_servers():
    with _lock:
        servers = [list(addr) for addr in _remote_servers.values()]
    try:
        with open(Config.LINK_POOL_CACHE, "w") as f:
            json.dump(servers, f)
    except Exception as e:
        logger.error(f"Failed to save server cache: {e}")


def _cleanup_seen_messages():
    now = time.time()
    with _lock:
        expired = [mid for mid, ts in _seen_messages.items() if now - ts > _MSG_TTL]
        for mid in expired:
            del _seen_messages[mid]


def _is_message_seen(msg_id: str) -> bool:
    with _lock:
        if msg_id in _seen_messages:
            return True
        _seen_messages[msg_id] = time.time()
        return False


def _mark_seen(msg_id: str):
    with _lock:
        _seen_messages[msg_id] = time.time()


def _broadcast(data: bytes, exclude_server: str = None):
    with _lock:
        targets = [
            (name, addr)
            for name, addr in _remote_servers.items()
            if name != exclude_server
        ]
    for name, addr in targets:
        try:
            _socket.sendto(data, addr)
        except Exception as e:
            logger.error(f"Failed to send to {name}({addr}): {e}")


def _pack_message(packet: dict) -> bytes:
    return snappy.compress(json.dumps(packet, separators=(",", ":")).encode())


def _unpack_message(data: bytes) -> dict:
    return json.loads(snappy.uncompress(data).decode())


def _send_to(packet: dict, addr):
    try:
        _socket.sendto(_pack_message(packet), addr)
        return True
    except Exception as e:
        logger.error(f"Failed to send to {addr}: {e}")
        return False


def _share_servers(target_addr):
    with _lock:
        servers = [list(addr) for addr in _remote_servers.values()]
    self_addr = list(Config.SELF_ADDR)
    if self_addr not in servers:
        servers.append(self_addr)
    msg_id = str(uuid.uuid4())
    _mark_seen(msg_id)
    _send_to(
        {"t": "servers", "id": msg_id, "o": Config.SERVER_NAME, "data": servers},
        target_addr,
    )


def _sync_players(target_addr):
    for session in get_session():
        msg_id = str(uuid.uuid4())
        _mark_seen(msg_id)
        packet = {
            "t": "players",
            "id": msg_id,
            "o": Config.SERVER_NAME,
            "info": [
                session.player_id,
                session.player_name,
                session.scene_id,
                session.channel_id,
                session.chat_channel_id,
                session.avatar_id,
                session.badge_id,
                base64.b64encode(session.scene_player.SerializeToString()).decode(),
            ],
        }
        _send_to(packet, target_addr)
        time.sleep(0.01)


def sync_player(session):
    msg_id = str(uuid.uuid4())
    _mark_seen(msg_id)
    packet = {
        "t": "players",
        "id": msg_id,
        "o": Config.SERVER_NAME,
        "info": [
            session.player_id,
            session.player_name,
            session.scene_id,
            session.channel_id,
            session.chat_channel_id,
            session.avatar_id,
            session.badge_id,
            base64.b64encode(session.scene_player.SerializeToString()).decode(),
        ],
    }

    with _lock:
        for _, addr in _remote_servers.items():
            _send_to(packet, addr)


def _on_new_server(server_name, addr):
    logger.info(f"New server connected: {server_name} at {addr}")
    time.sleep(0.1)
    _share_servers(addr)
    _sync_players(addr)
    _save_servers()


def _connect_server(server_addr):
    server_addr = tuple(server_addr)
    if server_addr == tuple(Config.SELF_ADDR):
        return False
    with _lock:
        for addr in _remote_servers.values():
            if addr == server_addr:
                return True
    _socket_ready.wait()
    for _ in range(3):
        try:
            _socket.sendto(_make_handshake(), server_addr)
            time.sleep(1)
            with _lock:
                for addr in _remote_servers.values():
                    if addr == server_addr:
                        return True
        except Exception:
            pass
    return False


def _heartbeat_thread():
    while True:
        time.sleep(_HEARTBEAT_INTERVAL)
        now = time.time()
        with _lock:
            servers = list(_remote_servers.items())
        handshake = _make_handshake()
        for name, addr in servers:
            try:
                _socket.sendto(handshake, addr)
            except Exception as e:
                logger.error(f"Failed to send heartbeat to {name}: {e}")
        with _lock:
            to_remove = [
                name
                for name, t in _last_heartbeat.items()
                if now - t > _HEARTBEAT_TIMEOUT
            ]
        for name in to_remove:
            _remove_server(name)
            logger.warning(f"Removed server {name} due to timeout")
            for session in session_list:
                if session.remote:
                    if session.server_name == name:
                        session.running = False
        if to_remove:
            _save_servers()
        _cleanup_seen_messages()


def _listen_thread():
    _socket.bind(Config.LINK_LISTEN)
    _socket_ready.set()
    logger.info(f"Link server listening on {Config.LINK_LISTEN}")

    while True:
        try:
            data, addr = _socket.recvfrom(65535)
        except Exception as e:
            logger.error(f"Error receiving data: {e}")
            continue

        server_name = _parse_handshake(data)
        if server_name:
            if server_name == Config.SERVER_NAME:
                continue
            is_new = _add_server(server_name, addr)
            if is_new:
                try:
                    _socket.sendto(_make_handshake(), addr)
                except Exception:
                    pass
                threading.Thread(
                    target=_on_new_server, args=(server_name, addr), daemon=True
                ).start()
            else:
                with _lock:
                    if server_name in _last_heartbeat:
                        _last_heartbeat[server_name] = time.time()
            continue

        sender_name = _get_server_name_by_addr(addr)
        if sender_name:
            with _lock:
                _last_heartbeat[sender_name] = time.time()

        try:
            packet = _unpack_message(data)
        except Exception as e:
            logger.error(f"Failed to unpack message from {addr}: {e}")
            continue

        msg_id = packet.get("id")
        msg_type = packet.get("t")
        origin = packet.get("o")

        if not msg_id or _is_message_seen(msg_id):
            continue
        if origin == Config.SERVER_NAME:
            continue

        if msg_type == "servers":
            for server_addr in packet.get("data", []):
                server_addr = tuple(server_addr)
                if server_addr == tuple(Config.SELF_ADDR):
                    continue
                with _lock:
                    known = any(
                        addr == server_addr for addr in _remote_servers.values()
                    )
                if not known:
                    threading.Thread(
                        target=_connect_server, args=(server_addr,), daemon=True
                    ).start()
            _broadcast(data, exclude_server=origin)

        elif msg_type == "players":
            info = packet.get("info")
            if info and origin:
                try:
                    session = RemoteSession(origin, info)
                    with lock_session:
                        session_list.append(session)
                    logger.info(
                        f"Added remote player {session.player_name} from {origin}"
                    )
                except Exception as e:
                    print(traceback.format_exc())
                    logger.error(f"Failed to create RemoteSession: {e}")

        elif msg_type == "data":
            player_id = packet.get("p")
            scene_id = packet.get("s")
            channel_id = packet.get("c")
            proto_msg_id = packet.get("m")
            payload_b64 = packet.get("b")
            if not all(
                [origin, scene_id is not None, channel_id is not None, payload_b64]
            ):
                continue
            try:
                payload = base64.b64decode(payload_b64)
                _message_handler(
                    origin, player_id, scene_id, channel_id, proto_msg_id, payload
                )
            except Exception as e:
                logger.error(f"Message handler error: {e}")
            _broadcast(data, exclude_server=origin)


def init():
    global _socket
    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    threading.Thread(target=_listen_thread, daemon=True).start()
    _socket_ready.wait()

    all_servers = set(_load_servers())
    if Config.LINK_OTHER_SERVER:
        all_servers.update(tuple(s) for s in Config.LINK_POOL)
    all_servers.discard(tuple(Config.SELF_ADDR))

    handshake = _make_handshake()
    for server_addr in all_servers:
        try:
            _socket.sendto(handshake, server_addr)
        except Exception:
            pass

    threading.Thread(target=_heartbeat_thread, daemon=True).start()
    time.sleep(1)
    _save_servers()

    with _lock:
        server_count = len(_remote_servers)
    logger.info(f"Link module initialized, connected to {server_count} servers")


def rsend(player_id: int, scene_id: int, channel_id: int, msg_id: int, msg):
    if player_id > 1010000:
        return
    msg_uuid = str(uuid.uuid4())
    _mark_seen(msg_uuid)
    packet = {
        "t": "data",
        "id": msg_uuid,
        "o": Config.SERVER_NAME,
        "p": player_id,
        "s": scene_id,
        "c": channel_id,
        "m": msg_id,
        "b": base64.b64encode(msg.SerializeToString()).decode(),
    }
    _broadcast(_pack_message(packet))


def get_connected_servers():
    with _lock:
        return list(_remote_servers.items())


def get_server_count():
    with _lock:
        return len(_remote_servers)


class RemoteSession(GameSession):
    def __init__(self, server_name, info):
        self.server_name = server_name
        self.player_id = _trans_player_id(server_name, info[0])
        self.player_name = info[1]
        self.scene_id = info[2]
        self.channel_id = info[3]
        self.chat_channel_id = info[4]
        self.avatar_id = info[5]
        self.badge_id = info[6]
        self.scene_player = pb.ScenePlayer()
        self.scene_player.ParseFromString(base64.b64decode(info[7]))
        self.scene_player.player_id = _trans_player_id(
            server_name, self.scene_player.player_id
        )
        self.pos = {}
        self.running = True
        self.verified = True
        self.logged_in = True
        self.remote = True

    def send(self, msg_id: int, message: Message, packet_id: int, is_bin: bool = False):
        pass
