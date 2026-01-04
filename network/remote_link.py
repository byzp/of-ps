import socket
import threading
import logging
import time
import uuid
import os
import json
import random
import struct
from datetime import datetime
from config import Config
from network.game_session import GameSession, snappy
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
_announced_addrs = set()
_server_ids = {}
_last_seen = {}
_seen_messages = {}
_lock = threading.Lock()
_socket = None
_socket_ready = threading.Event()
_server_name = (
    Config.SERVER_NAME
    + "&"
    + str(uuid.uuid4())[:8]
    + "&"
    + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)
_name_lock = threading.Lock()

_kcp_manager = None
_addr_to_conv = {}
_conv_to_addr = {}
_conv_lock = threading.Lock()

_pending_negotiations = {}
_negotiation_lock = threading.Lock()

_queued_messages = {}
_queue_lock = threading.Lock()

KCP_IMPORT_FAILED = False
_MSG_TTL = 60
_HEARTBEAT_INTERVAL = 3
_SERVER_TIMEOUT = 8
_NEGOTIATE_TIMEOUT = 5
_MAX_NEGOTIATE_ATTEMPTS = 10

PACKET_TYPE_NEGOTIATE = 0x01
PACKET_TYPE_KCP = 0x02

try:
    from utils.kcp import KCPManager
except Exception:
    KCP_IMPORT_FAILED = True


def _get_name():
    with _name_lock:
        return _server_name


def _generate_conv():
    return random.randint(1, 0x7FFFFFFF)


def _trans_player_id(server_name, player_id):
    with _lock:
        if server_name not in _server_ids:
            _server_ids[server_name] = (len(_server_ids) + 1) * 10000
        return _server_ids[server_name] + player_id


def _resolve_name_conflict():
    global _server_name
    _server_name += str(uuid.uuid4())[:8]
    return _server_name


def _add_server(name, addr):
    with _lock:
        is_new = name not in _remote_servers
        _remote_servers[name] = addr
        _last_seen[name] = time.time()
        if is_new and name not in _server_ids:
            _server_ids[name] = (len(_server_ids) + 1) * 10000
    return is_new


def _update_last_seen(name):
    with _lock:
        if name in _remote_servers:
            _last_seen[name] = time.time()


def _add_announced_addr(addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    with _lock:
        _announced_addrs.add(addr_tuple)


def _remove_announced_addr(addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    with _lock:
        _announced_addrs.discard(addr_tuple)


def _cleanup_kcp_for_addr(addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    conv = None
    with _conv_lock:
        conv = _addr_to_conv.pop(addr_tuple, None)
        if conv is not None:
            _conv_to_addr.pop(conv, None)

    if conv is not None and _kcp_manager:
        _kcp_manager.remove(conv)

    with _queue_lock:
        _queued_messages.pop(addr_tuple, None)


def _remove_server(name):
    with _lock:
        addr = _remote_servers.pop(name, None)
        _last_seen.pop(name, None)

    if addr:
        _remove_announced_addr(addr)
        _cleanup_kcp_for_addr(addr)


def _is_conv_in_use(conv):
    with _conv_lock:
        return conv in _conv_to_addr


def _get_conv_for_addr(addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    with _conv_lock:
        return _addr_to_conv.get(addr_tuple)


def _register_conv(conv, addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    with _conv_lock:
        if conv in _conv_to_addr:
            if _conv_to_addr[conv] != addr_tuple:
                return False
            return True
        if addr_tuple in _addr_to_conv:
            return _addr_to_conv[addr_tuple] == conv
        _conv_to_addr[conv] = addr_tuple
        _addr_to_conv[addr_tuple] = conv
        return True


def _send_raw(data, addr):
    if _socket:
        _socket.sendto(data, addr)


def _send_negotiate(addr, neg_type, conv):
    neg = pb.LinkNegotiate()
    neg.type = neg_type
    neg.conv = conv
    neg.server_name = _get_name()
    payload = neg.SerializeToString()
    data = struct.pack("!B", PACKET_TYPE_NEGOTIATE) + payload
    _send_raw(data, addr)


def _start_negotiation(addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr

    with _conv_lock:
        if addr_tuple in _addr_to_conv:
            return True

    with _negotiation_lock:
        if addr_tuple in _pending_negotiations:
            pending = _pending_negotiations[addr_tuple]
            if time.time() - pending["last_time"] < _NEGOTIATE_TIMEOUT:
                return False

    conv = _generate_conv()
    attempts = 0
    while _is_conv_in_use(conv) and attempts < 100:
        conv = _generate_conv()
        attempts += 1

    with _negotiation_lock:
        _pending_negotiations[addr_tuple] = {
            "conv": conv,
            "attempts": 1,
            "last_time": time.time(),
        }

    _send_negotiate(addr, pb.LinkNegotiate.PROPOSE, conv)
    return False


def _handle_negotiate(payload, addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr

    try:
        neg = pb.LinkNegotiate()
        neg.ParseFromString(payload)
    except Exception:
        return

    if neg.type == pb.LinkNegotiate.PROPOSE:
        with _conv_lock:
            if addr_tuple in _addr_to_conv:
                existing_conv = _addr_to_conv[addr_tuple]
                _send_negotiate(addr, pb.LinkNegotiate.ACCEPT, existing_conv)
                return

        if _is_conv_in_use(neg.conv):
            _send_negotiate(addr, pb.LinkNegotiate.CONFLICT, neg.conv)
        else:
            if _register_conv(neg.conv, addr_tuple):
                _send_negotiate(addr, pb.LinkNegotiate.ACCEPT, neg.conv)
                _on_conv_established(neg.conv, addr_tuple, neg.server_name)
            else:
                _send_negotiate(addr, pb.LinkNegotiate.CONFLICT, neg.conv)

    elif neg.type == pb.LinkNegotiate.ACCEPT:
        with _negotiation_lock:
            pending = _pending_negotiations.pop(addr_tuple, None)

        if pending:
            conv = neg.conv
            if _register_conv(conv, addr_tuple):
                _on_conv_established(conv, addr_tuple, neg.server_name)

    elif neg.type == pb.LinkNegotiate.CONFLICT:
        with _negotiation_lock:
            pending = _pending_negotiations.get(addr_tuple)
            if not pending:
                return
            if pending["attempts"] >= _MAX_NEGOTIATE_ATTEMPTS:
                _pending_negotiations.pop(addr_tuple, None)
                return
            new_conv = _generate_conv()
            attempts = 0
            while _is_conv_in_use(new_conv) and attempts < 100:
                new_conv = _generate_conv()
                attempts += 1
            pending["conv"] = new_conv
            pending["attempts"] += 1
            pending["last_time"] = time.time()

        _send_negotiate(addr, pb.LinkNegotiate.PROPOSE, new_conv)


def _on_conv_established(conv, addr, server_name):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr

    if _kcp_manager:
        _kcp_manager.get_or_create(conv)

    is_new = _add_server(server_name, addr_tuple)
    if is_new:
        threading.Thread(
            target=_on_new_server, args=(server_name, addr_tuple), daemon=True
        ).start()

    _flush_queued_messages(addr_tuple)


def _flush_queued_messages(addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    with _queue_lock:
        queued = _queued_messages.pop(addr_tuple, [])

    conv = _get_conv_for_addr(addr_tuple)
    if not conv or not _kcp_manager:
        return

    session = _kcp_manager.get_or_create(conv)
    for data in queued:
        session.send(data)


def _output_factory(conv):
    def output(kcp_data):
        with _conv_lock:
            addr = _conv_to_addr.get(conv)
        if addr and _socket:
            packet = pb.LinkPacket()
            packet.conv = conv
            packet.kcp_data = kcp_data
            payload = packet.SerializeToString()
            data = struct.pack("!B", PACKET_TYPE_KCP) + payload
            _socket.sendto(data, addr)

    return output


def _make_msg(msg_type):
    msg = pb.LinkMessage()
    msg.id = str(uuid.uuid4())
    msg.origin = _get_name()
    msg.type = msg_type
    with _lock:
        _seen_messages[msg.id] = time.time()
    return msg


def _pack(msg):
    return snappy.compress(msg.SerializeToString())


def _unpack(data):
    msg = pb.LinkMessage()
    msg.ParseFromString(snappy.uncompress(data))
    return msg


def _send_to(msg, addr):
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr
    conv = _get_conv_for_addr(addr_tuple)
    data = _pack(msg)

    if conv is None:
        with _queue_lock:
            if addr_tuple not in _queued_messages:
                _queued_messages[addr_tuple] = []
            _queued_messages[addr_tuple].append(data)
        _start_negotiation(addr_tuple)
        return

    if _kcp_manager:
        session = _kcp_manager.get_or_create(conv)
        session.send(data)


def _broadcast(msg, exclude=None):
    data = _pack(msg)
    with _lock:
        targets = [(n, a) for n, a in _remote_servers.items() if n != exclude]
    for name, addr in targets:
        conv = _get_conv_for_addr(addr)
        if conv:
            session = _kcp_manager.get_or_create(conv)
            session.send(data)


def _is_seen(msg_id):
    with _lock:
        if msg_id in _seen_messages:
            return True
        _seen_messages[msg_id] = time.time()
        return False


def _cleanup():
    now = time.time()
    with _lock:
        expired_msgs = [m for m, t in _seen_messages.items() if now - t > _MSG_TTL]
        for m in expired_msgs:
            del _seen_messages[m]

    with _negotiation_lock:
        expired_neg = []
        for addr, info in _pending_negotiations.items():
            if now - info["last_time"] > _NEGOTIATE_TIMEOUT:
                if info["attempts"] < _MAX_NEGOTIATE_ATTEMPTS:
                    info["attempts"] += 1
                    info["last_time"] = now
                    new_conv = _generate_conv()
                    while _is_conv_in_use(new_conv):
                        new_conv = _generate_conv()
                    info["conv"] = new_conv
                    _send_negotiate(addr, pb.LinkNegotiate.PROPOSE, new_conv)
                else:
                    expired_neg.append(addr)
        for addr in expired_neg:
            _pending_negotiations.pop(addr, None)

    with _queue_lock:
        expired_queues = []
        for addr in list(_queued_messages.keys()):
            with _conv_lock:
                if addr not in _addr_to_conv:
                    with _negotiation_lock:
                        if addr not in _pending_negotiations:
                            expired_queues.append(addr)
        for addr in expired_queues:
            _queued_messages.pop(addr, None)


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
        try:
            with open(Config.LINK_POOL_CACHE, "r") as f:
                return [tuple(a) for a in json.load(f)]
        except Exception:
            return []
    return []


def _save_cache():
    with _lock:
        self_addr = tuple(Config.SELF_ADDR)
        servers = [list(a) for a in _announced_addrs if a != self_addr]
    try:
        with open(Config.LINK_POOL_CACHE, "w") as f:
            json.dump(servers, f)
    except Exception:
        pass


def _share_servers(addr):
    msg = _make_msg(pb.LinkMessage.SERVERS)
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr

    with _lock:
        for a in _announced_addrs:
            if a != addr_tuple:
                sa = msg.addrs.add()
                sa.host, sa.port = a

    if Config.SELF_ADDR_IS_PUBLIC:
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


def _process_message(data, addr, origin_server=None):
    try:
        msg = _unpack(data)
    except Exception:
        return

    origin = msg.origin

    if not msg.id or _is_seen(msg.id):
        return

    if msg.type == pb.LinkMessage.NAME_CONFLICT:
        new_name = _resolve_name_conflict()
        logger.info(f"Name conflict, new name: {new_name}")
        retry_msg = _make_msg(pb.LinkMessage.HEARTBEAT)
        _send_to(retry_msg, addr)
        return

    if origin == _get_name():
        conflict_msg = _make_msg(pb.LinkMessage.NAME_CONFLICT)
        _send_to(conflict_msg, addr)
        return

    _update_last_seen(origin)

    if msg.type == pb.LinkMessage.HEARTBEAT:
        pass

    elif msg.type == pb.LinkMessage.SERVERS:
        for sa in msg.addrs:
            sa_tuple = (sa.host, sa.port)
            if sa_tuple == tuple(Config.SELF_ADDR):
                continue

            _add_announced_addr(sa_tuple)

            with _lock:
                known = sa_tuple in _remote_servers.values()
            if not known:
                _start_negotiation(sa_tuple)

        _broadcast(msg, exclude=origin)

    elif msg.type == pb.LinkMessage.PLAYER:
        info = msg.player_info
        trans_id = _trans_player_id(origin, info.player_id)
        exists = False
        for session_t in get_session():
            if session_t.player_id == trans_id:
                exists = True
                break
        if not exists:
            session = RemoteSession(origin, info)
            with lock_session:
                session_list.append(session)
            logger.info(
                f"Remote player {session.player_name}({session.player_id}) from {origin}"
            )
            _broadcast(msg, exclude=origin)

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
    with _conv_lock:
        addr = _conv_to_addr.pop(conv, None)
        if addr:
            _addr_to_conv.pop(addr, None)


def _heartbeat():
    while True:
        time.sleep(_HEARTBEAT_INTERVAL)

        msg = _make_msg(pb.LinkMessage.HEARTBEAT)
        _broadcast(msg)

        now = time.time()
        with _lock:
            expired = [n for n, t in _last_seen.items() if now - t > _SERVER_TIMEOUT]
        for name in expired:
            _remove_server(name)
            logger.warning(f"Server {name} timed out")
            for s in list(session_list):
                if (
                    getattr(s, "remote", False)
                    and getattr(s, "server_name", "") == name
                ):
                    s.running = False
        if expired:
            _save_cache()

        _cleanup()


def _handle_kcp_packet(payload, addr):
    try:
        packet = pb.LinkPacket()
        packet.ParseFromString(payload)
    except Exception:
        return

    conv = packet.conv
    addr_tuple = tuple(addr) if not isinstance(addr, tuple) else addr

    with _conv_lock:
        if conv in _conv_to_addr:
            if _conv_to_addr[conv] != addr_tuple:
                return
        elif addr_tuple in _addr_to_conv:
            if _addr_to_conv[addr_tuple] != conv:
                return
        else:
            return

    if _kcp_manager and packet.kcp_data:
        _kcp_manager.input(packet.kcp_data)


def _listen():
    _socket.bind(Config.LINK_LISTEN)
    _socket_ready.set()
    logger.info(f"Listening on {Config.LINK_LISTEN}")

    while True:
        try:
            data, addr = _socket.recvfrom(65535)
        except Exception:
            continue

        if len(data) < 2:
            continue

        packet_type = struct.unpack("!B", data[:1])[0]
        payload = data[1:]

        if packet_type == PACKET_TYPE_NEGOTIATE:
            _handle_negotiate(payload, addr)
        elif packet_type == PACKET_TYPE_KCP:
            _handle_kcp_packet(payload, addr)


def init():
    if not Config.LINK_OTHER_SERVER:
        return
    if KCP_IMPORT_FAILED:
        logger.warning("KCP import failed. Link module disabled.")
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

    for addr in Config.LINK_POOL:
        _add_announced_addr(tuple(addr))

    if Config.SELF_ADDR_IS_PUBLIC:
        _add_announced_addr(tuple(Config.SELF_ADDR))
        logger.info("Server configured as PUBLIC")
    else:
        logger.info("Server configured as NAT/private")

    for addr in servers:
        _start_negotiation(addr)

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
