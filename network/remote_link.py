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
from proto.net_pb2 import (
    LinkNegotiate,
    LinkPacket,
    LinkMessage,
    SendActionNotice,
    SceneActionType,
    ServerSceneSyncDataNotice,
    ChatMsgNotice,
    PlayerSceneSyncDataNotice,
    PlayerInfo,
    ScenePlayer,
)
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

HEARTBEAT_INTERVAL = 3.0
PEER_TIMEOUT = 9.0  # 须小于KCP层的10s死亡判定
NEGOTIATE_INTERVAL = 1.0
NEGOTIATE_MAX_TRIES = 5
RECONNECT_MIN = 5.0
RECONNECT_MAX = 60.0
SEEN_MSG_TTL = 60.0
MAX_QUEUED_MSGS = 256

DISCONNECTED = 0
CONNECTING = 1
CONNECTED = 2


class _Link:
    """一个对端地址的连接状态机, 所有字段仅在持有 _lock 时读写"""

    __slots__ = (
        "addr",
        "state",
        "conv",
        "server_name",
        "last_seen",
        "queued",
        "next_try",
        "tries",
        "reconnect_delay",
        "ever_connected",
        "is_public",
        "peer_names",
        "subs",
        "subs_valid",
    )

    def __init__(self, addr):
        self.addr = addr
        self.state = DISCONNECTED
        self.conv = 0
        self.server_name = ""
        self.last_seen = 0.0
        self.queued = []
        self.next_try = 0.0
        self.tries = 0
        self.reconnect_delay = RECONNECT_MIN
        self.ever_connected = False
        self.is_public = False  # 对端声明其地址可被直连
        self.peer_names = set()  # 对端心跳上报的直连服务器名(用于二跳路由)
        self.subs = set()  # 对端订阅的场景 (scene_id<<32|channel_id)
        self.subs_valid = False  # 未收到订阅上报时按"全订阅"处理


# _lock 保护以下所有状态。
# 加锁纪律: 持有 _lock 期间禁止调用 _kcp 的任何方法、socket 收发、
# 以及 scene_data / lock_session 相关函数, 只做纯内存读写。
# 这保证了与 KCP 内部锁和场景锁之间不存在环路, 不可能死锁。
_links = {}  # addr -> _Link
_conv_to_addr = {}  # conv -> addr (含握手中预留的conv)
_server_ids = {}  # server_name -> 玩家id偏移
_seen_msgs = {}  # msg.id -> time (广播去重)
_lock = threading.Lock()
_cache_dirty = False
_socket = None
_kcp = None
_name = (
    f"{Config.SERVER_NAME}&{uuid.uuid4().hex[:8]}&{datetime.now():%Y-%m-%d %H:%M:%S}"
)

try:
    KCP_IMPORT_FAILED = False
    from utils.kcp import KCPManager, get_conv, OVERHEAD
except Exception:
    KCP_IMPORT_FAILED = True


def _trans_id(server, pid):
    with _lock:
        if server not in _server_ids:
            _server_ids[server] = (len(_server_ids) + 1) * 10000
        return _server_ids[server] + pid


def _send_raw(data, addr):
    # UDP发送失败不能把异常抛给调用线程(心跳/监听/KCP更新线程)
    try:
        if _socket is not None:
            _socket.sendto(data, addr)
    except OSError as e:
        logger.debug(f"sendto {addr} failed: {e}")


def _send_neg(addr, ntype, conv):
    neg = LinkNegotiate(
        type=ntype,
        conv=conv,
        server_name=_name,
        is_public=bool(Config.SELF_ADDR_IS_PUBLIC),
    )
    _send_raw(struct.pack("!B", PACKET_NEGOTIATE) + neg.SerializeToString(), addr)


def _alloc_conv_locked():
    while True:
        conv = random.randint(1, 0x7FFFFFFF)
        if conv not in _conv_to_addr:
            return conv


def _release_conv_locked(link):
    old = link.conv
    if old and _conv_to_addr.get(old) == link.addr:
        del _conv_to_addr[old]
    link.conv = 0
    return old or None


def _begin_connect_locked(link, now):
    """进入握手状态并预留conv, 返回应发送PROPOSE的conv"""
    _release_conv_locked(link)
    link.state = CONNECTING
    link.conv = _alloc_conv_locked()
    _conv_to_addr[link.conv] = link.addr
    link.tries = 1
    link.next_try = now + NEGOTIATE_INTERVAL
    return link.conv


def _establish_locked(link, conv, server_name, now, is_public):
    """置为已连接, 返回交给 _after_connected 在锁外执行的上下文"""
    global _cache_dirty
    prev_name = link.server_name if link.state == CONNECTED else ""
    old_conv = _release_conv_locked(link)
    link.state = CONNECTED
    link.conv = conv
    link.server_name = server_name
    link.last_seen = now
    link.tries = 0
    link.reconnect_delay = RECONNECT_MIN
    link.is_public = is_public
    # 每次建立连接都是新的会话, 路由/订阅信息等对方心跳重新上报
    link.peer_names = set()
    link.subs = set()
    link.subs_valid = False
    if not link.ever_connected:
        link.ever_connected = True
        _cache_dirty = True
    _conv_to_addr[conv] = link.addr
    if server_name not in _server_ids:
        _server_ids[server_name] = (len(_server_ids) + 1) * 10000
    queued, link.queued = link.queued, []
    return (link.addr, conv, server_name, queued, old_conv, prev_name)


def _after_connected(ctx):
    addr, conv, server_name, queued, old_conv, prev_name = ctx
    if old_conv and old_conv != conv:
        _kcp.remove(old_conv)
    if prev_name:
        # 已连接状态下对方提议了新conv => 对端重启过, 旧远程会话作废等待重新同步
        _drop_remote_sessions(prev_name)
    session = _kcp.get_or_create(conv)
    for data in queued:
        session.send(data)
    logger.info(f"Server connected: {server_name} at {addr}")
    threading.Thread(
        target=_on_new_server, args=(server_name, addr), daemon=True
    ).start()


def _connect(addr, force=False):
    """确保与addr建立连接; 已在握手/已连接时为空操作, force=True忽略重连退避"""
    addr = tuple(addr)
    if addr == tuple(Config.SELF_ADDR):
        return
    now = time.monotonic()
    with _lock:
        link = _links.get(addr)
        if link is None:
            link = _Link(addr)
            _links[addr] = link
        if link.state != DISCONNECTED:
            return
        if not force and now < link.next_try:
            return
        conv = _begin_connect_locked(link, now)
    _send_neg(addr, LinkNegotiate.PROPOSE, conv)


def _disconnect(addr, reason):
    now = time.monotonic()
    with _lock:
        link = _links.get(addr)
        if link is None or link.state == DISCONNECTED:
            return
        old_conv = _release_conv_locked(link)
        name = link.server_name
        link.state = DISCONNECTED
        link.queued.clear()
        link.tries = 0
        link.next_try = now + link.reconnect_delay
        link.reconnect_delay = min(link.reconnect_delay * 2, RECONNECT_MAX)
    logger.warning(f"Server disconnected: {name or addr} ({reason})")
    if old_conv:
        _kcp.remove(old_conv)
    if name:
        _drop_remote_sessions(name)


def _drop_remote_sessions(name):
    with lock_session:
        for s in session_list:
            if getattr(s, "remote", False) and getattr(s, "server_name", "") == name:
                s.running = False


def _on_negotiate(payload, addr):
    addr = tuple(addr)
    neg = LinkNegotiate()
    neg.ParseFromString(payload)
    now = time.monotonic()

    if neg.type == LinkNegotiate.PROPOSE:
        reply = None
        established = None
        with _lock:
            other = _conv_to_addr.get(neg.conv)
            if other is not None and other != addr:
                # conv已被其他对端占用
                reply = (LinkNegotiate.CONFLICT, neg.conv)
            else:
                link = _links.get(addr)
                if link is None:
                    link = _Link(addr)
                    _links[addr] = link
                if link.state == CONNECTED and link.conv == neg.conv:
                    # 对方没收到ACCEPT重发了PROPOSE, 幂等应答
                    reply = (LinkNegotiate.ACCEPT, neg.conv)
                elif link.state == CONNECTING and neg.conv < link.conv:
                    # 双方同时PROPOSE: 统一采用较大的conv, 对方会接受我们的提议
                    pass
                elif link.state == CONNECTING and neg.conv == link.conv:
                    reply = (LinkNegotiate.CONFLICT, neg.conv)
                else:
                    # 未连接 / 同时PROPOSE中对方conv更大 / 对端重启换了conv
                    established = _establish_locked(
                        link, neg.conv, neg.server_name, now, neg.is_public
                    )
                    reply = (LinkNegotiate.ACCEPT, neg.conv)
        if reply is not None:
            _send_neg(addr, reply[0], reply[1])
        if established is not None:
            _after_connected(established)

    elif neg.type == LinkNegotiate.ACCEPT:
        established = None
        with _lock:
            link = _links.get(addr)
            if link is not None and link.state == CONNECTING:
                other = _conv_to_addr.get(neg.conv)
                if other is None or other == addr:
                    established = _establish_locked(
                        link, neg.conv, neg.server_name, now, neg.is_public
                    )
        if established is not None:
            _after_connected(established)

    elif neg.type == LinkNegotiate.CONFLICT:
        conv = None
        with _lock:
            link = _links.get(addr)
            if link is not None and link.state == CONNECTING:
                conv = _begin_connect_locked(link, now)
        if conv is not None:
            _send_neg(addr, LinkNegotiate.PROPOSE, conv)


def _output(conv):
    def fn(kcp_data):
        with _lock:
            addr = _conv_to_addr.get(conv)
        if addr:
            pkt = LinkPacket(conv=conv, kcp_data=kcp_data)
            _send_raw(struct.pack("!B", PACKET_KCP) + pkt.SerializeToString(), addr)

    return fn


def _pack(msg):
    return snappy.compress(msg.SerializeToString())


def _unpack(data):
    msg = LinkMessage()
    msg.ParseFromString(snappy.uncompress(data))
    return msg


def _make_msg(mtype):
    with _lock:
        msg = LinkMessage(id=uuid.uuid4().hex, origin=_name, type=mtype)
        _seen_msgs[msg.id] = time.time()
    return msg


def _send_to(msg, addr):
    addr = tuple(addr)
    data = _pack(msg)
    conv = None
    with _lock:
        link = _links.get(addr)
        if link is None:
            link = _Link(addr)
            _links[addr] = link
        if link.state == CONNECTED:
            conv = link.conv
        elif len(link.queued) < MAX_QUEUED_MSGS:
            link.queued.append(data)
    if conv is not None:
        _kcp.send(conv, data)
    else:
        # 未连接: 消息已排队, 确保握手在进行
        _connect(addr)


def _broadcast(msg, exclude=None):
    """控制面泛洪: 发给全部直连对端(SERVERS/PLAYER等低频消息用, 接收方会继续转发)"""
    data = _pack(msg)
    with _lock:
        convs = [
            l.conv
            for l in _links.values()
            if l.state == CONNECTED and l.server_name != exclude
        ]
    for conv in convs:
        _kcp.send(conv, data)


def _sub_key(scene_id, channel_id):
    return (int(scene_id) << 32) | (int(channel_id) & 0xFFFFFFFF)


def _local_subs():
    """本服有本地玩家的场景集合"""
    subs = set()
    for s in get_session():
        if s.player_id < 1010000:
            subs.add(_sub_key(s.scene_id, s.channel_id))
    return subs


def _broadcast_data(msg, interest=None):
    """数据面按需直发, 不做盲目泛洪:
    - 直连对端: interest为场景key时只发给订阅了该场景的(未上报订阅的按全订阅处理);
    - 只能二跳到达的服务器(NAT-NAT): 确定性地(名字最小者)指派一个共同邻居中转,
      写进relay_to字段, 中转方只转发给点名的目标; 订阅未知, 一律发送。
    每条消息共发送 <= N-1 次, 取代原来 (N-1)^2 次的泛洪。"""
    with _lock:
        my = _name
        connected = {}  # name -> conv (全部直连)
        wanted = set()  # 其中按订阅需要接收的
        for l in _links.values():
            if l.state != CONNECTED:
                continue
            connected[l.server_name] = l.conv
            if interest is None or not l.subs_valid or interest in l.subs:
                wanted.add(l.server_name)
        relay_plan = {}  # 中转方name -> [二跳目标name]
        assigned = set()
        for l in sorted(
            (x for x in _links.values() if x.state == CONNECTED),
            key=lambda x: x.server_name,
        ):
            for pn in sorted(l.peer_names):
                if pn == my or pn in connected or pn in assigned:
                    continue
                assigned.add(pn)
                relay_plan.setdefault(l.server_name, []).append(pn)

    targets = []  # (conv, relay_to)
    for name, conv in connected.items():
        rt = relay_plan.get(name, ())
        if rt or name in wanted:
            targets.append((conv, rt))
    if not targets:
        return
    plain = None
    for conv, rt in targets:
        if rt:
            del msg.relay_to[:]
            msg.relay_to.extend(rt)
            _kcp.send(conv, _pack(msg))
        else:
            if plain is None:
                del msg.relay_to[:]
                plain = _pack(msg)
            _kcp.send(conv, plain)
    del msg.relay_to[:]


def _relay_data(msg):
    """执行DATA消息里的中转指令: 只转发给relay_to点名且当前直连的服务器"""
    targets = set(msg.relay_to)
    if not targets:
        return
    del msg.relay_to[:]
    with _lock:
        convs = [
            l.conv
            for l in _links.values()
            if l.state == CONNECTED and l.server_name in targets
        ]
    if convs:
        data = _pack(msg)
        for conv in convs:
            _kcp.send(conv, data)


def _handle_data(origin, datas, mid, payload):
    if mid == 1970:
        rsp = SendActionNotice()
        rsp.ParseFromString(payload)
        rsp.from_player_id = _trans_id(origin, rsp.from_player_id)
        up_action(datas[0], datas[1], rsp)
    elif mid == 1208:
        rsp = ServerSceneSyncDataNotice()
        rsp.ParseFromString(payload)
        for d in rsp.data:
            d.player_id = _trans_id(origin, d.player_id)
            for sd in d.server_data:
                if sd.action_type == SceneActionType.SceneActionType_ENTER:
                    for s in get_session():
                        if s.player_id == d.player_id:
                            s.scene_id, s.channel_id = datas[0], datas[1]
                            break
                if sd.player.player_id:
                    sd.player.player_id = _trans_id(origin, sd.player.player_id)
        up_scene_action(datas[0], datas[1], rsp)
    elif mid == 1936:
        rsp = ChatMsgNotice()
        rsp.ParseFromString(payload)
        rsp.msg.player_id = _trans_id(origin, rsp.msg.player_id)
        up_chat_msg(datas[0], datas[1], datas[2], rsp)
    elif mid == 1206:
        rsp = PlayerSceneSyncDataNotice()
        rsp.ParseFromString(payload)
        for d in rsp.data:
            d.player_id = _trans_id(origin, d.player_id)
            up_recorder(datas[0], datas[1], d.player_id, d.data[0])


def _share_servers(addr):
    addr = tuple(addr)
    msg = _make_msg(LinkMessage.SERVERS)
    with _lock:
        for link in _links.values():
            # 只分享声明了公网可达的地址; NAT后的对端地址分享出去也连不上
            if link.state == CONNECTED and link.is_public and link.addr != addr:
                msg.addrs.add(host=link.addr[0], port=link.addr[1])
    if Config.SELF_ADDR_IS_PUBLIC:
        msg.addrs.add(host=Config.SELF_ADDR[0], port=Config.SELF_ADDR[1])
    _send_to(msg, addr)


def _sync_players(addr):
    for s in get_session():
        if s.player_id < 1010000:
            msg = _make_msg(LinkMessage.PLAYER)
            msg.player_info.CopyFrom(
                PlayerInfo(
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
    msg = _make_msg(LinkMessage.PLAYER)
    msg.player_info.CopyFrom(
        PlayerInfo(
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
    _share_servers(addr)
    _sync_players(addr)


def _add_remote_player(origin, info):
    # RemoteSession构造内会拿 _lock(_trans_id), 必须在 lock_session 之外完成
    session = RemoteSession(origin, info)
    with lock_session:
        for s in session_list:
            if s.player_id == session.player_id and s.running and s.logged_in:
                return False
        session_list.append(session)
    logger.info(f"Remote player {info.player_name}({info.player_id}) from {origin}")
    return True


def _process(data, addr):
    global _name
    msg = _unpack(data)
    now = time.monotonic()
    with _lock:
        if msg.id in _seen_msgs:
            return
        _seen_msgs[msg.id] = time.time()
        my_name = _name
        # 能从该地址收到KCP数据即证明对端存活
        link = _links.get(addr)
        if link is not None and link.state == CONNECTED:
            link.last_seen = now
        # 中转来的消息同样刷新原始服务器的存活时间
        if msg.origin != my_name:
            for l in _links.values():
                if l.state == CONNECTED and l.server_name == msg.origin:
                    l.last_seen = now
                    break

    if msg.origin == my_name:
        _send_to(_make_msg(LinkMessage.NAME_CONFLICT), addr)
        return

    if msg.type == LinkMessage.HEARTBEAT:
        if msg.has_state:
            # 心跳携带对端的直连列表和场景订阅, 用于二跳路由与数据面过滤
            with _lock:
                link = _links.get(addr)
                if (
                    link is not None
                    and link.state == CONNECTED
                    and link.server_name == msg.origin
                ):
                    link.peer_names = set(msg.peer_names)
                    link.subs = set(msg.subs)
                    link.subs_valid = True

    elif msg.type == LinkMessage.NAME_CONFLICT:
        with _lock:
            _name += uuid.uuid4().hex[:8]
        _send_to(_make_msg(LinkMessage.HEARTBEAT), addr)

    elif msg.type == LinkMessage.SERVERS:
        for sa in msg.addrs:
            sa_tuple = (sa.host, sa.port)
            if sa_tuple != tuple(Config.SELF_ADDR):
                _connect(sa_tuple)
        _broadcast(msg, exclude=msg.origin)

    elif msg.type == LinkMessage.PLAYER:
        if _add_remote_player(msg.origin, msg.player_info):
            _broadcast(msg, exclude=msg.origin)

    elif msg.type == LinkMessage.DATA:
        _handle_data(msg.origin, list(msg.datas), msg.msg_id, msg.payload)
        _relay_data(msg)


def _on_recv(conv, data):
    with _lock:
        addr = _conv_to_addr.get(conv)
    if addr is None:
        return
    try:
        _process(data, addr)
    except Exception:
        # KCPManager会静默吞掉回调异常, 在这里记录
        logger.exception(f"Error processing link message from {addr}")


def _on_dead(conv):
    with _lock:
        addr = _conv_to_addr.get(conv)
    if addr:
        _disconnect(addr, "kcp timeout")


def _on_kcp_packet(payload, addr):
    pkt = LinkPacket()
    pkt.ParseFromString(payload)
    addr = tuple(addr)
    with _lock:
        link = _links.get(addr)
        ok = (
            link is not None
            and link.state == CONNECTED
            and link.conv == pkt.conv
            and len(pkt.kcp_data) >= OVERHEAD
            and get_conv(pkt.kcp_data) == pkt.conv
        )
    if ok:
        # 必须在锁外调用: input会在本线程同步触发output回调
        _kcp.input(pkt.kcp_data)


def _listen():
    while True:
        try:
            data, addr = _socket.recvfrom(65535)
        except OSError as e:
            logger.debug(f"recv error. {e}")
            time.sleep(0.05)
            continue
        try:
            if len(data) < 2:
                continue
            ptype, payload = data[0], data[1:]
            if ptype == PACKET_NEGOTIATE:
                _on_negotiate(payload, addr)
            elif ptype == PACKET_KCP:
                _on_kcp_packet(payload, addr)
        except Exception as e:
            # 单个报文的解析/处理错误(畸形数据、端口扫描等)不能杀死监听线程
            logger.debug(f"bad packet from {addr}: {e}")


def _make_state_heartbeat():
    """携带直连列表+场景订阅的心跳"""
    subs = _local_subs()
    msg = _make_msg(LinkMessage.HEARTBEAT)
    msg.has_state = True
    msg.subs.extend(subs)
    with _lock:
        msg.peer_names.extend(
            l.server_name for l in _links.values() if l.state == CONNECTED
        )
    return msg, subs


def _maintenance():
    global _cache_dirty
    last_heartbeat = 0.0
    last_prune = 0.0
    last_subs = None
    while True:
        try:
            time.sleep(1.0)
            now = time.monotonic()

            proposes = []
            timeouts = []
            with _lock:
                for link in _links.values():
                    if link.state == CONNECTING and now >= link.next_try:
                        if link.tries >= NEGOTIATE_MAX_TRIES:
                            # 握手失败, 退避后重试
                            _release_conv_locked(link)
                            link.state = DISCONNECTED
                            link.queued.clear()
                            link.next_try = now + link.reconnect_delay
                            link.reconnect_delay = min(
                                link.reconnect_delay * 2, RECONNECT_MAX
                            )
                        else:
                            link.tries += 1
                            link.next_try = now + NEGOTIATE_INTERVAL
                            proposes.append((link.addr, link.conv))
                    elif link.state == DISCONNECTED and now >= link.next_try:
                        proposes.append((link.addr, _begin_connect_locked(link, now)))
                    elif (
                        link.state == CONNECTED and now - link.last_seen > PEER_TIMEOUT
                    ):
                        timeouts.append(link.addr)

            for addr, conv in proposes:
                _send_neg(addr, LinkNegotiate.PROPOSE, conv)
            for addr in timeouts:
                _disconnect(addr, "heartbeat timeout")

            # 订阅集变化(玩家换场景/上下线)时立即发心跳, 缩短对端过滤表的滞后
            if now - last_heartbeat >= HEARTBEAT_INTERVAL or (
                last_subs is not None and _local_subs() != last_subs
            ):
                last_heartbeat = now
                msg, last_subs = _make_state_heartbeat()
                _broadcast(msg)

            if now - last_prune >= 10.0:
                last_prune = now
                t = time.time()
                with _lock:
                    for m in [
                        k for k, ts in _seen_msgs.items() if t - ts > SEEN_MSG_TTL
                    ]:
                        del _seen_msgs[m]

            with _lock:
                dirty = _cache_dirty
                _cache_dirty = False
            if dirty:
                _save_cache()
        except Exception:
            logger.exception("Link maintenance error")


def _load_cache():
    try:
        if os.path.exists(Config.LINK_POOL_CACHE):
            with open(Config.LINK_POOL_CACHE) as f:
                return [tuple(a) for a in json.load(f)]
    except (OSError, ValueError) as e:
        logger.warning(f"load link cache failed: {e}")
    return []


def _save_cache():
    with _lock:
        data = [
            list(l.addr)
            for l in _links.values()
            if l.ever_connected and l.is_public and l.addr != tuple(Config.SELF_ADDR)
        ]
    try:
        with open(Config.LINK_POOL_CACHE, "w") as f:
            json.dump(data, f)
    except OSError as e:
        logger.warning(f"save link cache failed: {e}")


def init():
    if not Config.LINK_OTHER_SERVER:
        return
    if KCP_IMPORT_FAILED:
        logger.warning("KCP import failed. Link module disabled.")
        return

    global _socket, _kcp
    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # 必须在第一次sendto前bind, 否则会占用临时端口导致对端回包到错误端口
    _socket.bind(Config.LINK_LISTEN)
    logger.info(f"Listening on {Config.LINK_LISTEN}")

    _kcp = KCPManager(output_factory=_output, on_recv=_on_recv, on_dead=_on_dead)
    _kcp.start_update_loop(interval_ms=10)

    threading.Thread(target=_listen, daemon=True, name="link-listen").start()
    threading.Thread(target=_maintenance, daemon=True, name="link-maintenance").start()

    servers = set(_load_cache()) | {tuple(s) for s in Config.LINK_POOL}
    servers.discard(tuple(Config.SELF_ADDR))
    for addr in servers:
        _connect(addr, force=True)


def rsend(msg_id, proto_msg, datas=None):
    if not Config.LINK_OTHER_SERVER:
        return
    msg = _make_msg(LinkMessage.DATA)
    if datas:
        msg.datas.extend(datas)
    msg.msg_id = msg_id
    msg.payload = proto_msg.SerializeToString()
    # 高频的动作(1970)/位置同步(1206)只发给对该场景感兴趣的服务器;
    # 1208(含进场事件,维护全局玩家目录)和1936(聊天,漏一条就是永久丢失)不过滤
    interest = None
    if msg_id in (1970, 1206) and datas and len(datas) >= 2:
        interest = _sub_key(datas[0], datas[1])
    _broadcast_data(msg, interest)


def get_connected_servers():
    with _lock:
        return [
            (l.server_name, l.addr) for l in _links.values() if l.state == CONNECTED
        ]


def get_server_count():
    with _lock:
        return sum(1 for l in _links.values() if l.state == CONNECTED)


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
        self.scene_player = ScenePlayer()
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
