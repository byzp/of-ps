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

PACKET_NEGOTIATE = 0x01
PACKET_KCP = 0x02

_servers = {}
_announced = set()
_server_ids = {}
_last_seen = {}
_seen_msgs = {}
_addr_to_conv = {}
_conv_to_addr = {}
_pending = {}
_queued = {}
_lock = threading.Lock()
_conv_lock = threading.Lock()
_socket = None
_kcp = None
_name = (
    f"{Config.SERVER_NAME}&{uuid.uuid4().hex[:8]}&{datetime.now():%Y-%m-%d %H:%M:%S}"
)

try:
    KCP_IMPORT_FAILED = False
    from utils.kcp import KCPManager
except Exception:
    KCP_IMPORT_FAILED = True


def _trans_id(server, pid):
    with _lock:
        if server not in _server_ids:
            _server_ids[server] = (len(_server_ids) + 1) * 10000
        return _server_ids[server] + pid


def _send_raw(data, addr):
    _socket.sendto(data, addr)


def _send_neg(addr, ntype, conv):
    neg = pb.LinkNegotiate(type=ntype, conv=conv, server_name=_name)
    _send_raw(struct.pack("!B", PACKET_NEGOTIATE) + neg.SerializeToString(), addr)


def _register(conv, addr):
    with _conv_lock:
        if conv in _conv_to_addr or addr in _addr_to_conv:
            return False
        _conv_to_addr[conv] = addr
        _addr_to_conv[addr] = conv
        return True


def _negotiate(addr):
    addr = tuple(addr)
    with _conv_lock:
        if addr in _addr_to_conv:
            return
    conv = random.randint(1, 0x7FFFFFFF)
    _pending[addr] = conv
    _send_neg(addr, pb.LinkNegotiate.PROPOSE, conv)


def _on_negotiate(payload, addr):
    addr = tuple(addr)
    neg = pb.LinkNegotiate()
    neg.ParseFromString(payload)

    if neg.type == pb.LinkNegotiate.PROPOSE:
        with _conv_lock:
            if addr in _addr_to_conv:
                _send_neg(addr, pb.LinkNegotiate.ACCEPT, _addr_to_conv[addr])
                return
        if _register(neg.conv, addr):
            _send_neg(addr, pb.LinkNegotiate.ACCEPT, neg.conv)
            _on_connected(neg.conv, addr, neg.server_name)
        else:
            _send_neg(addr, pb.LinkNegotiate.CONFLICT, neg.conv)

    elif neg.type == pb.LinkNegotiate.ACCEPT:
        _pending.pop(addr, None)
        if _register(neg.conv, addr):
            _on_connected(neg.conv, addr, neg.server_name)

    elif neg.type == pb.LinkNegotiate.CONFLICT:
        conv = random.randint(1, 0x7FFFFFFF)
        _pending[addr] = conv
        _send_neg(addr, pb.LinkNegotiate.PROPOSE, conv)


def _on_connected(conv, addr, server):
    _kcp.get_or_create(conv)
    with _lock:
        is_new = server not in _servers
        _servers[server] = addr
        _last_seen[server] = time.time()
        _announced.add(addr)
        if server not in _server_ids:
            _server_ids[server] = (len(_server_ids) + 1) * 10000

    for data in _queued.pop(addr, []):
        _kcp.get_or_create(conv).send(data)

    if is_new:
        threading.Thread(
            target=_on_new_server, args=(server, addr), daemon=True
        ).start()


def _output(conv):
    def fn(kcp_data):
        with _conv_lock:
            addr = _conv_to_addr.get(conv)
        if addr:
            pkt = pb.LinkPacket(conv=conv, kcp_data=kcp_data)
            _send_raw(struct.pack("!B", PACKET_KCP) + pkt.SerializeToString(), addr)

    return fn


def _pack(msg):
    return snappy.compress(msg.SerializeToString())


def _unpack(data):
    msg = pb.LinkMessage()
    msg.ParseFromString(snappy.uncompress(data))
    return msg


def _make_msg(mtype):
    msg = pb.LinkMessage(id=uuid.uuid4().hex, origin=_name, type=mtype)
    with _lock:
        _seen_msgs[msg.id] = time.time()
    return msg


def _send_to(msg, addr):
    addr = tuple(addr)
    data = _pack(msg)
    with _conv_lock:
        conv = _addr_to_conv.get(addr)
    if conv:
        _kcp.get_or_create(conv).send(data)
    else:
        _queued.setdefault(addr, []).append(data)
        _negotiate(addr)


def _broadcast(msg, exclude=None):
    data = _pack(msg)
    with _lock:
        targets = [a for n, a in _servers.items() if n != exclude]
    for addr in targets:
        with _conv_lock:
            conv = _addr_to_conv.get(addr)
        if conv:
            _kcp.get_or_create(conv).send(data)


def _handle_data(origin, datas, mid, payload):
    if mid == 1970:
        rsp = pb.SendActionNotice()
        rsp.ParseFromString(payload)
        rsp.from_player_id = _trans_id(origin, rsp.from_player_id)
        up_action(datas[0], datas[1], rsp)
    elif mid == 1208:
        rsp = pb.ServerSceneSyncDataNotice()
        rsp.ParseFromString(payload)
        for d in rsp.data:
            d.player_id = _trans_id(origin, d.player_id)
            for sd in d.server_data:
                if sd.action_type == pb.SceneActionType_ENTER:
                    for s in get_session():
                        if s.player_id == d.player_id:
                            s.scene_id, s.channel_id = datas[0], datas[1]
                            break
                if sd.player.player_id:
                    sd.player.player_id = _trans_id(origin, sd.player.player_id)
        up_scene_action(datas[0], datas[1], rsp)
    elif mid == 1936:
        rsp = pb.ChatMsgNotice()
        rsp.ParseFromString(payload)
        rsp.msg.player_id = _trans_id(origin, rsp.msg.player_id)
        up_chat_msg(datas[0], datas[1], datas[2], rsp)
    elif mid == 1206:
        rsp = pb.PlayerSceneSyncDataNotice()
        rsp.ParseFromString(payload)
        for d in rsp.data:
            d.player_id = _trans_id(origin, d.player_id)
            up_recorder(datas[0], datas[1], d.player_id, d.data[0])


def _share_servers(addr):
    msg = _make_msg(pb.LinkMessage.SERVERS)
    with _lock:
        for a in _announced:
            if a != tuple(addr):
                msg.addrs.add(host=a[0], port=a[1])
    if Config.SELF_ADDR_IS_PUBLIC:
        msg.addrs.add(host=Config.SELF_ADDR[0], port=Config.SELF_ADDR[1])
    _send_to(msg, addr)


def _sync_players(addr):
    for s in get_session():
        if s.player_id < 1010000:
            msg = _make_msg(pb.LinkMessage.PLAYER)
            msg.player_info.CopyFrom(
                pb.PlayerInfo(
                    player_id=s.player_id,
                    player_name=s.player_name,
                    scene_id=s.scene_id,
                    channel_id=s.channel_id,
                    chat_channel_id=s.chat_channel_id,
                    avatar_id=s.avatar_id,
                    badge_id=s.badge_id,
                    scene_player=s.scene_player.SerializeToString(),
                )
            )
            _send_to(msg, addr)


def sync_player(session):
    msg = _make_msg(pb.LinkMessage.PLAYER)
    msg.player_info.CopyFrom(
        pb.PlayerInfo(
            player_id=session.player_id,
            player_name=session.player_name,
            scene_id=session.scene_id,
            channel_id=session.channel_id,
            chat_channel_id=session.chat_channel_id,
            avatar_id=session.avatar_id,
            badge_id=session.badge_id,
            scene_player=session.scene_player.SerializeToString(),
        )
    )
    _broadcast(msg)


def _on_new_server(name, addr):
    logger.info(f"Server connected: {name} at {addr}")
    _share_servers(addr)
    _sync_players(addr)
    _save_cache()


def _process(data, addr):
    global _name
    msg = _unpack(data)
    with _lock:
        if msg.id in _seen_msgs:
            return
        _seen_msgs[msg.id] = time.time()

    if msg.origin == _name:
        _send_to(_make_msg(pb.LinkMessage.NAME_CONFLICT), addr)
        return

    with _lock:
        if msg.origin in _servers:
            _last_seen[msg.origin] = time.time()

    if msg.type == pb.LinkMessage.NAME_CONFLICT:
        _name += uuid.uuid4().hex[:8]
        _send_to(_make_msg(pb.LinkMessage.HEARTBEAT), addr)

    elif msg.type == pb.LinkMessage.SERVERS:
        for sa in msg.addrs:
            sa_tuple = (sa.host, sa.port)
            if sa_tuple != tuple(Config.SELF_ADDR):
                with _lock:
                    _announced.add(sa_tuple)
                    if sa_tuple not in _servers.values():
                        _negotiate(sa_tuple)
        _broadcast(msg, exclude=msg.origin)

    elif msg.type == pb.LinkMessage.PLAYER:
        trans_id = _trans_id(msg.origin, msg.player_info.player_id)
        if not any(s.player_id == trans_id for s in get_session()):
            with lock_session:
                session_list.append(RemoteSession(msg.origin, msg.player_info))
                logger.info(
                    f"Remote player {msg.player_info.player_name}({msg.player_info.player_id}) from {msg.origin}"
                )
            _broadcast(msg, exclude=msg.origin)

    elif msg.type == pb.LinkMessage.DATA:
        _handle_data(msg.origin, list(msg.datas), msg.msg_id, msg.payload)
        _broadcast(msg, exclude=msg.origin)


def _on_recv(conv, data):
    with _conv_lock:
        addr = _conv_to_addr.get(conv)
    if addr:
        _process(data, addr)


def _on_dead(conv):
    with _conv_lock:
        addr = _conv_to_addr.pop(conv, None)
        if addr:
            _addr_to_conv.pop(addr, None)


def _heartbeat():
    while True:
        time.sleep(3)
        _broadcast(_make_msg(pb.LinkMessage.HEARTBEAT))

        now = time.time()
        with _lock:
            expired = [n for n, t in _last_seen.items() if now - t > 8]

        for name in expired:
            with _lock:
                logger.warning(f"Server {name} timed out")
                addr = _servers.pop(name, None)
                _last_seen.pop(name, None)
            if addr:
                with _conv_lock:
                    conv = _addr_to_conv.pop(addr, None)
                    if conv:
                        _conv_to_addr.pop(conv, None)
                        _kcp.remove(conv)
            for s in list(session_list):
                if (
                    getattr(s, "remote", False)
                    and getattr(s, "server_name", "") == name
                ):
                    s.running = False

        with _lock:
            for m in [m for m, t in _seen_msgs.items() if now - t > 60]:
                del _seen_msgs[m]


def _on_kcp_packet(payload, addr):
    pkt = pb.LinkPacket()
    pkt.ParseFromString(payload)
    addr = tuple(addr)
    with _conv_lock:
        if pkt.conv in _conv_to_addr and _conv_to_addr[pkt.conv] == addr:
            _kcp.input(pkt.kcp_data)


def _listen():
    _socket.bind(Config.LINK_LISTEN)
    logger.info(f"Listening on {Config.LINK_LISTEN}")

    while True:
        try:
            data, addr = _socket.recvfrom(65535)
        except Exception as e:
            logger.debug(f"recv error. {e}")
            continue
        if len(data) < 2:
            continue
        ptype, payload = data[0], data[1:]
        if ptype == PACKET_NEGOTIATE:
            _on_negotiate(payload, addr)
        elif ptype == PACKET_KCP:
            _on_kcp_packet(payload, addr)


def _load_cache():
    if os.path.exists(Config.LINK_POOL_CACHE):
        with open(Config.LINK_POOL_CACHE) as f:
            return [tuple(a) for a in json.load(f)]
    return []


def _save_cache():
    with _lock:
        data = [list(a) for a in _announced if a != tuple(Config.SELF_ADDR)]
    with open(Config.LINK_POOL_CACHE, "w") as f:
        json.dump(data, f)


def init():
    if not Config.LINK_OTHER_SERVER:
        return
    if KCP_IMPORT_FAILED:
        logger.warning("KCP import failed. Link module disabled.")
        return

    global _socket, _kcp
    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _kcp = KCPManager(output_factory=_output, on_recv=_on_recv, on_dead=_on_dead)
    _kcp.start_update_loop(interval_ms=10)

    threading.Thread(target=_listen, daemon=True).start()

    servers = set(_load_cache()) | {tuple(s) for s in Config.LINK_POOL}
    servers.discard(tuple(Config.SELF_ADDR))

    for addr in Config.LINK_POOL:
        _announced.add(tuple(addr))
    if Config.SELF_ADDR_IS_PUBLIC:
        _announced.add(tuple(Config.SELF_ADDR))

    for addr in servers:
        _negotiate(addr)

    threading.Thread(target=_heartbeat, daemon=True).start()
    time.sleep(1)
    _save_cache()


def rsend(msg_id, proto_msg, datas=[]):
    if not Config.LINK_OTHER_SERVER:
        return
    msg = _make_msg(pb.LinkMessage.DATA)
    msg.datas.extend(datas)
    msg.msg_id = msg_id
    msg.payload = proto_msg.SerializeToString()
    _broadcast(msg)


def get_connected_servers():
    with _lock:
        return list(_servers.items())


def get_server_count():
    with _lock:
        return len(_servers)


class RemoteSession(GameSession):
    def __init__(self, server_name, info):
        self.server_name = server_name
        self.player_id = _trans_id(server_name, info.player_id)
        self.player_name = info.player_name
        self.scene_id = info.scene_id
        self.channel_id = info.channel_id
        self.chat_channel_id = info.chat_channel_id
        self.avatar_id = info.avatar_id
        self.badge_id = info.badge_id
        self.scene_player = pb.ScenePlayer()
        self.scene_player.ParseFromString(info.scene_player)
        self.scene_player.player_id = _trans_id(
            server_name, self.scene_player.player_id
        )
        self.pos = {}
        self.running = True
        self.verified = True
        self.logged_in = True
        self.remote = True

    def send(self, msg_id, message, packet_id, is_bin=False):
        pass
