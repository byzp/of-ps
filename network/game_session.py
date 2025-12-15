import logging
import struct
import socket
from collections import deque
from threading import Lock, Event, Thread
from google.protobuf.message import Message

try:
    import snappy_py as snappy  # http://github.com/byzp/snappy-py
except ImportError:
    import snappy
from config import Config
from proto import OverField_pb2
from network.packet_factory import PacketFactory

logger = logging.getLogger(__name__)

# 预编译常量
_HEADER_STRUCT = struct.Struct(">H")
_UNAUTH_CMDS = frozenset((1001, 1007, 2201, 2203))
_NOSEQ_CMDS = frozenset((1002, 1004, 1006, 1008))
_COMPRESS_THRESHOLD = Config.COMPRESS_THRESHOLD


class SendTask:
    __slots__ = ("msg_id", "data", "packet_id", "is_bin")

    def __init__(self, msg_id, data, packet_id, is_bin):
        self.msg_id = msg_id
        self.data = data
        self.packet_id = packet_id
        self.is_bin = is_bin


class GameSession:

    __slots__ = (
        "socket",
        "address",
        "_recv_buf",
        "_recv_len",
        "_recv_mv",
        "_send_queue",
        "_send_lock",
        "_send_event",
        "_send_thread",
        "_seq_id",
        # 预分配的临时 buffer
        "_write_head_buf",
        # 玩家状态
        "player_id",
        "player_name",
        "scene_id",
        "channel_id",
        "chat_channel_id",
        "avatar_id",
        "badge_id",
        "scene_player",
        "running",
        "verified",
        "logged_in",
    )

    HEADER_LENGTH = 2
    _RECV_BUF_SIZE = 65536
    _SEND_BATCH_LIMIT = 50  # 每次最多从队列取多少包

    def __init__(self, client_socket: socket.socket, address):
        self.socket = client_socket
        self.address = address

        # TCP优化
        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 524288)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)

        self._recv_buf = bytearray(self._RECV_BUF_SIZE)
        self._recv_mv = memoryview(self._recv_buf)
        self._recv_len = 0

        self._send_queue: deque[SendTask] = deque()
        self._send_lock = Lock()
        self._send_event = Event()

        self._write_head_buf = bytearray(128)

        self._seq_id = 1

        self.player_id = None
        self.player_name = None
        self.scene_id = 1
        self.channel_id = 1
        self.chat_channel_id = 1
        self.avatar_id = 41101
        self.badge_id = 0
        self.scene_player = OverField_pb2.ScenePlayer()

        self.running = True
        self.verified = False
        self.logged_in = False

    def run(self):
        self._send_thread = Thread(
            target=self._send_loop, daemon=True, name=f"sender-{self.address}"
        )
        self._send_thread.start()

        recv_mv = self._recv_mv
        sock = self.socket

        try:
            while self.running:
                # 直接读入 view 切片
                n = sock.recv_into(recv_mv[self._recv_len :])
                if n == 0:
                    break
                self._recv_len += n
                self._process_buffer()
        except OSError:
            pass
        except Exception as e:
            logger.exception(f"Session error: {e}")
        finally:
            self.close()

    def _process_buffer(self):
        buf = self._recv_buf
        pos = 0
        end = self._recv_len

        while pos + 2 <= end:
            hlen = _HEADER_STRUCT.unpack_from(buf, pos)[0]
            hend = pos + 2 + hlen
            if hend > end:
                break

            head = OverField_pb2.PacketHead()
            head.ParseFromString(bytes(self._recv_mv[pos + 2 : hend]))

            msg_id = head.msg_id
            logger.debug(f"Received message: {msg_id}")
            # 阻止未授权访问
            if not self.verified and msg_id not in _UNAUTH_CMDS:
                self.close()
                return

            pend = hend + head.body_len
            if pend > end:
                break

            body = bytes(self._recv_mv[hend:pend])
            if head.flag == 1:
                body = snappy.uncompress(body)

            PacketFactory.process_packet(msg_id, body, head.packet_id, self)
            pos = pend

        if pos > 0:
            rem = end - pos
            if rem > 0:
                self._recv_buf[:rem] = self._recv_buf[pos:end]
            self._recv_len = rem

    def send(self, msg_id: int, message: Message, packet_id: int, is_bin: bool = False):
        logger.debug(f"Sending message: {msg_id}")
        if not self.running:
            return

        # 防止message被修改导致并发问题
        data_bytes = message if is_bin else message.SerializeToString()

        # 构造任务对象
        task = SendTask(msg_id, data_bytes, packet_id, is_bin)

        # 入队
        with self._send_lock:
            self._send_queue.append(task)
            # 队列之前为空时才设置事件, 减少syscall
            if len(self._send_queue) == 1:
                self._send_event.set()

    def sbin(self, msg_id: int, path: str, packet_id: int):
        try:
            with open(path, "rb") as f:
                self.send(msg_id, f.read(), packet_id, is_bin=True)
        except FileNotFoundError:
            logger.error(f"File not found: {path}")

    def _send_loop(self):
        sock = self.socket
        queue = self._send_queue
        lock = self._send_lock
        event = self._send_event

        # 减少内存碎片
        out_buf = bytearray(65536)

        # 避免频繁创建销毁
        head_proto = OverField_pb2.PacketHead()

        while self.running:
            event.wait()
            tasks = []
            with lock:
                # 一次性取空,减少锁竞争
                while queue and len(tasks) < self._SEND_BATCH_LIMIT:
                    tasks.append(queue.popleft())

                if not queue:
                    event.clear()
                else:
                    pass

            if not tasks:
                continue

            current_offset = 0

            for task in tasks:
                body = task.data
                body_len = len(body)

                flag = 0
                if body_len > _COMPRESS_THRESHOLD:
                    flag = 1
                    body = snappy.compress(body)
                    body_len = len(body)

                head_proto.Clear()
                head_proto.msg_id = task.msg_id
                if task.packet_id:
                    head_proto.packet_id = task.packet_id
                head_proto.flag = flag
                head_proto.body_len = body_len

                if task.msg_id in _NOSEQ_CMDS:
                    head_proto.seq_id = 0
                else:
                    head_proto.seq_id = self._seq_id
                    self._seq_id += 1

                h_data = head_proto.SerializeToString()
                h_len = len(h_data)

                total_pkt_len = 2 + h_len + body_len

                required_size = current_offset + total_pkt_len
                if required_size > len(out_buf):
                    new_size = max(len(out_buf) * 2, required_size + 8192)
                    new_buf = bytearray(new_size)
                    new_buf[:current_offset] = out_buf[:current_offset]
                    out_buf = new_buf

                _HEADER_STRUCT.pack_into(out_buf, current_offset, h_len)

                out_buf[current_offset + 2 : current_offset + 2 + h_len] = h_data

                body_start = current_offset + 2 + h_len
                out_buf[body_start : body_start + body_len] = body

                current_offset += total_pkt_len

            # 批量发送 IO
            if current_offset > 0:
                try:
                    # memoryview 避免切片复制
                    sock.sendall(memoryview(out_buf)[:current_offset])
                except OSError:
                    self.close()
                    break
                except Exception as e:
                    logger.error(f"Send loop error: {e}")
                    self.close()
                    break

    def close(self):
        if not self.running:
            return
        self.running = False
        self._send_event.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.socket.close()
        except OSError:
            pass
