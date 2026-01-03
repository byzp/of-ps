import socket
import threading
import logging
import time
import uuid
import os
import json
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
from utils.kcp import KCPManager, get_conv, OVERHEAD

logger = logging.getLogger(__name__)

_remote_servers = {}
_server_ids = {}
_last_seen = {}
_seen_messages = {}
_lock = threading.Lock()
_socket = None
_socket_ready = threading.Event()
_server_name = Config.SERVER_NAME
_name_lock = threading.Lock()

_kcp_manager = None
_addr_to_conv = {}
_conv_to_addr = {}
_conv_created_at = {}  # Track when each conv was created for pending timeout
_next_conv = 1
_conv_lock = threading.Lock()

_MSG_TTL = 60
_HEARTBEAT_INTERVAL = 3
_SERVER_TIMEOUT = 10
_PENDING_TIMEOUT = 30  # Timeout for pending connections that never established


def _get_name():
    with _name_lock:
        return _server_name


def _trans_player_id(server_name, player_id):
    with _lock:
        if server_name not in _server_ids:
            _server_ids[server_name] = (len(_server_ids) + 1) * 10000
        return _server_ids[server_name] + player_id


def _resolve_name_conflict():
    global _server_name
    _server_name += str(uuid.uuid4())
    return _server_name


def _add_server(name, addr):
    with _lock:
        is_new = name not in _remote_servers
        _remote_servers[name] = addr
        _last_seen[name] = time.time()
        if is_new and name not in _server_ids:
            _server_ids[name] = (len(_server_ids) + 1) * 10000
    return is_new


def _cleanup_kcp_for_addr(addr):
    """Clean up KCP connection and conv/addr mappings for an address."""
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    conv = None
    with _conv_lock:
        conv = _addr_to_conv.pop(addr_tuple, None)
        if conv is not None:
            _conv_to_addr.pop(conv, None)
            _conv_created_at.pop(conv, None)

    if conv is not None and _kcp_manager:
        _kcp_manager.remove(conv)
        logger.debug(f"Cleaned up KCP session {conv} for {addr_tuple}")


def _remove_server(name):
    with _lock:
        addr = _remote_servers.pop(name, None)
        _last_seen.pop(name, None)

    # Clean up KCP connection for this server
    if addr:
        _cleanup_kcp_for_addr(addr)


def _cleanup_orphaned_connections():
    """Clean up KCP sessions for addresses that failed to establish connection."""
    with _lock:
        known_addrs = set(
            tuple(a) if not isinstance(a, tuple) else a
            for a in _remote_servers.values()
        )

    now = time.time()
    orphaned = []
    with _conv_lock:
        for addr, conv in list(_addr_to_conv.items()):
            if addr not in known_addrs:
                created_at = _conv_created_at.get(conv, 0)
                if now - created_at > _PENDING_TIMEOUT:
                    orphaned.append((addr, conv))

    for addr, conv in orphaned:
        with _conv_lock:
            _addr_to_conv.pop(addr, None)
            _conv_to_addr.pop(conv, None)
            _conv_created_at.pop(conv, None)
        if _kcp_manager:
            _kcp_manager.remove(conv)
            logger.debug(f"Cleaned up orphaned KCP session {conv} (connection timeout)")


def _get_or_assign_conv(addr):
    global _next_conv
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    with _conv_lock:
        if addr_tuple in _addr_to_conv:
            return _addr_to_conv[addr_tuple]
        conv = _next_conv
        _next_conv += 1
        _addr_to_conv[addr_tuple] = conv
        _conv_to_addr[conv] = addr_tuple
        _conv_created_at[conv] = time.time()  # Track creation time
        return conv


def _register_conv_addr(conv, addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    with _conv_lock:
        if conv not in _conv_to_addr:
            _conv_to_addr[conv] = addr_tuple
            _addr_to_conv[addr_tuple] = conv
            if conv not in _conv_created_at:
                _conv_created_at[conv] = time.time()


def _output_factory(conv):
    def output(data):
        with _conv_lock:
            addr = _conv_to_addr.get(conv)
        if addr and _socket:
            _socket.sendto(data, addr)

    return output


def _make_msg(msg_type):
    msg = pb.LinkMessage()
    msg.id = str(uuid.uuid4())
    msg.origin = _get_name()
    msg.type = msg_type
    _mark_seen(msg.id)
    return msg


def _pack(msg):
    return snappy.compress(msg.SerializeToString())


def _unpack(data):
    msg = pb.LinkMessage()
    msg.ParseFromString(snappy.uncompress(data))
    return msg


def _send_to(msg, addr):
    conv = _get_or_assign_conv(addr)
    session = _kcp_manager.get_or_create(conv)
    session.send(_pack(msg))


def _broadcast(msg, exclude=None):
    data = _pack(msg)
    with _lock:
        targets = [(n, a) for n, a in _remote_servers.items() if n != exclude]
    for name, addr in targets:
        conv = _get_or_assign_conv(addr)
        session = _kcp_manager.get_or_create(conv)
        session.send(data)


def _is_seen(msg_id):
    with _lock:
        if msg_id in _seen_messages:
            return True
        _seen_messages[msg_id] = time.time()
        return False


def _mark_seen(msg_id):
    with _lock:
        _seen_messages[msg_id] = time.time()


def _cleanup():
    now = time.time()
    with _lock:
        for m in [m for m, t in _seen_messages.items() if now - t > _MSG_TTL]:
            del _seen_messages[m]


def _handle_data(origin, pid, sid, cid, mid, payload):
    pid = _trans_player_id(origin, pid)
    if mid == 1970:
        rsp = pb.SendActionNotice()
        rsp.ParseFromString(payload)
        up_action(pid, rsp.from_player_name, sid, cid, rsp.action_id)
    elif mid == 1208:
        rsp = pb.ServerSceneSyncDataNotice()
        rsp.ParseFromString(payload)
        for d in rsp.data:
            d.player_id = _trans_player_id(origin, d.player_id)
            for sd in d.server_data:
                if sd.action_type == pb.SceneActionType_ENTER:
                    for s in get_session():
                        if s.player_id == d.player_id:
                            s.scene_id = sid
                            s.channel_id = cid
                            break
                if sd.player.player_id:
                    sd.player.player_id = _trans_player_id(origin, sd.player.player_id)
        up_scene_action(sid, cid, rsp)
    elif mid == 1936:
        rsp = pb.ChatMsgNotice()
        rsp.ParseFromString(payload)
        up_chat_msg(rsp.type, pid, rsp.msg.text, rsp.msg.expression, sid, cid)
    elif mid == 1206:
        rsp = pb.PlayerSceneSyncDataNotice()
        rsp.ParseFromString(payload)
        for d in rsp.data:
            d.player_id = _trans_player_id(origin, d.player_id)
            up_recorder(sid, cid, d.player_id, d.data[0])


def _load_cache():
    if os.path.exists(Config.LINK_POOL_CACHE):
        with open(Config.LINK_POOL_CACHE, "r") as f:
            return [tuple(a) for a in json.load(f)]
    return []


def _save_cache():
    with _lock:
        servers = [list(a) for a in _remote_servers.values()]
    with open(Config.LINK_POOL_CACHE, "w") as f:
        json.dump(servers, f)


def _share_servers(addr):
    msg = _make_msg(pb.LinkMessage.SERVERS)
    with _lock:
        for a in _remote_servers.values():
            sa = msg.addrs.add()
            sa.host, sa.port = a
    sa = msg.addrs.add()
    sa.host, sa.port = Config.SELF_ADDR
    _send_to(msg, addr)


def _sync_players(addr):
    for s in get_session():
        if s.player_id < 1010000:
            msg = _make_msg(pb.LinkMessage.PLAYER)
            i = msg.player_info
            i.player_id, i.player_name = s.player_id, s.player_name
            i.scene_id, i.channel_id = s.scene_id, s.channel_id
            i.chat_channel_id, i.avatar_id, i.badge_id = (
                s.chat_channel_id,
                s.avatar_id,
                s.badge_id,
            )
            i.scene_player = s.scene_player.SerializeToString()
            _send_to(msg, addr)


def sync_player(session):
    msg = _make_msg(pb.LinkMessage.PLAYER)
    i = msg.player_info
    i.player_id, i.player_name = session.player_id, session.player_name
    i.scene_id, i.channel_id = session.scene_id, session.channel_id
    i.chat_channel_id, i.avatar_id, i.badge_id = (
        session.chat_channel_id,
        session.avatar_id,
        session.badge_id,
    )
    i.scene_player = session.scene_player.SerializeToString()
    _broadcast(msg)


def _on_new_server(name, addr):
    logger.info(f"Server connected: {name} at {addr}")
    _share_servers(addr)
    _sync_players(addr)
    _save_cache()


def _process_message(data, addr):
    try:
        msg = _unpack(data)
    except Exception:
        return

    origin = msg.origin

    if not msg.id or _is_seen(msg.id):
        return

    if msg.type == pb.LinkMessage.NAME_CONFLICT:
        logger.warning(
            f"Received name conflict notification from {addr}, need to change name"
        )
        new_name = _resolve_name_conflict()
        logger.info(f"Reconnecting with new name: {new_name}")
        retry_msg = _make_msg(pb.LinkMessage.HEARTBEAT)
        _send_to(retry_msg, addr)
        return

    if origin == _get_name():
        logger.warning(
            f"Name conflict detected! Remote server {addr} has same name '{origin}'"
        )
        logger.warning(f"Sending NAME_CONFLICT to {addr}, requesting rename")
        conflict_msg = _make_msg(pb.LinkMessage.NAME_CONFLICT)
        _send_to(conflict_msg, addr)
        return

    is_new = _add_server(origin, addr)
    if is_new:
        threading.Thread(
            target=_on_new_server, args=(origin, addr), daemon=True
        ).start()

    if msg.type == pb.LinkMessage.SERVERS:
        for sa in msg.addrs:
            sa_tuple = (sa.host, sa.port)
            if sa_tuple == tuple(Config.SELF_ADDR):
                continue
            with _lock:
                known = sa_tuple in _remote_servers.values()
            if not known:
                hello_msg = _make_msg(pb.LinkMessage.HEARTBEAT)
                _send_to(hello_msg, sa_tuple)
        _broadcast(msg, exclude=origin)

    elif msg.type == pb.LinkMessage.PLAYER:
        info = msg.player_info
        session = RemoteSession(origin, info)
        for session_t in get_session():
            pid = _trans_player_id(origin, session_t.player_id)
            if session_t.player_id == pid:
                continue
        with lock_session:
            session_list.append(session)
        logger.info(
            f"Remote player {session.player_name}({session.player_id}) from {origin}"
        )

    elif msg.type == pb.LinkMessage.DATA:
        _handle_data(
            origin,
            msg.player_id,
            msg.scene_id,
            msg.channel_id,
            msg.msg_id,
            msg.payload,
        )
        _broadcast(msg, exclude=origin)


def _on_kcp_recv(conv, data):
    with _conv_lock:
        addr = _conv_to_addr.get(conv)
    if addr:
        _process_message(data, addr)


def _on_kcp_dead(conv):
    # This callback may never be triggered, but keep it for completeness
    with _conv_lock:
        addr = _conv_to_addr.pop(conv, None)
        if addr:
            _addr_to_conv.pop(addr, None)
        _conv_created_at.pop(conv, None)
    logger.error(f"KCP session {conv} died")


def _heartbeat():
    while True:
        time.sleep(_HEARTBEAT_INTERVAL)
        msg = _make_msg(pb.LinkMessage.HEARTBEAT)
        _broadcast(msg)
        now = time.time()
        with _lock:
            expired = [n for n, t in _last_seen.items() if now - t > _SERVER_TIMEOUT]
        for name in expired:
            _remove_server(name)  # This now also cleans up KCP
            logger.warning(f"Server {name} timed out")
            for s in session_list:
                if (
                    getattr(s, "remote", False)
                    and getattr(s, "server_name", "") == name
                ):
                    s.running = False
        if expired:
            _save_cache()
        # Clean up orphaned connections (failed to establish)
        _cleanup_orphaned_connections()
        _cleanup()


def _listen():
    _socket.bind(Config.LINK_LISTEN)
    _socket_ready.set()
    logger.info(f"Listening on {Config.LINK_LISTEN}")

    while True:
        try:
            data, addr = _socket.recvfrom(65535)
        except Exception:
            continue

        if len(data) < OVERHEAD:
            continue

        conv = get_conv(data)
        _register_conv_addr(conv, addr)
        _kcp_manager.input(data)


def init():
    if not Config.LINK_OTHER_SERVER:
        return
    global _socket, _kcp_manager
    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    _kcp_manager = KCPManager(
        output_factory=_output_factory,
        on_recv=_on_kcp_recv,
        on_dead=_on_kcp_dead,
    )
    _kcp_manager.start_update_loop(interval_ms=10)

    threading.Thread(target=_listen, daemon=True).start()
    _socket_ready.wait()

    servers = set(_load_cache())
    servers.update(tuple(s) for s in Config.LINK_POOL)
    servers.discard(tuple(Config.SELF_ADDR))

    for addr in servers:
        msg = _make_msg(pb.LinkMessage.HEARTBEAT)
        _send_to(msg, addr)

    threading.Thread(target=_heartbeat, daemon=True).start()
    time.sleep(1)
    _save_cache()
    logger.info(
        f"Initialized as '{_get_name()}', {len(_remote_servers)} servers connected"
    )


def rsend(player_id, scene_id, channel_id, msg_id, proto_msg):
    if player_id > 1010000:
        return
    msg = _make_msg(pb.LinkMessage.DATA)
    msg.player_id = player_id
    msg.scene_id = scene_id
    msg.channel_id = channel_id
    msg.msg_id = msg_id
    msg.payload = proto_msg.SerializeToString()
    _broadcast(msg)


def get_connected_servers():
    with _lock:
        return list(_remote_servers.items())


def get_server_count():
    with _lock:
        return len(_remote_servers)


class RemoteSession(GameSession):
    def __init__(self, server_name, info):
        self.server_name = server_name
        self.player_id = _trans_player_id(server_name, info.player_id)
        self.player_name = info.player_name
        self.scene_id = info.scene_id
        self.channel_id = info.channel_id
        self.chat_channel_id = info.chat_channel_id
        self.avatar_id = info.avatar_id
        self.badge_id = info.badge_id
        self.scene_player = pb.ScenePlayer()
        self.scene_player.ParseFromString(info.scene_player)
        self.scene_player.player_id = _trans_player_id(
            server_name, self.scene_player.player_id
        )
        self.pos = {}
        self.running = True
        self.verified = True
        self.logged_in = True
        self.remote = True

    def send(self, msg_id, message, packet_id, is_bin=False):
        pass
