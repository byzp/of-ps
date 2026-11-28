import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from typing import Dict

from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler
from proto import net_pb2
from utils.scanner import scan_handlers

logger = logging.getLogger(__name__)

id_to_name = {
    v: k
    for k, v in vars(MsgId).items()
    if not k.startswith("__") and isinstance(v, int)
}


class PacketFactory:
    _handlers: Dict[int, PacketHandler] = {}
    _executor: ThreadPoolExecutor = None
    _state_lock = RLock()
    _accepting = False
    _pending = set()
    _pending_sizes = {}
    _pending_bytes = 0
    MAX_PENDING_PACKETS = max(32, Config.PACKET_POOL_MAX_WORKERS * 8)
    MAX_PENDING_BYTES = 32 * 1024 * 1024

    # 需要同步处理的
    _SYNC_CMDS = frozenset(
        (
            1001,
            1003,
            1005,
            MsgId.ChangeSceneChannelReq,
            MsgId.PlayerSceneRecordReq,
        )
    )

    @classmethod
    def initialize_handlers(cls, package_name: str):
        """Register handlers and create one bounded packet worker pool."""
        cls.shutdown()
        executor = ThreadPoolExecutor(
            max_workers=Config.PACKET_POOL_MAX_WORKERS, thread_name_prefix="packet"
        )
        try:
            handler_classes = scan_handlers(package_name)
            handlers = {}
            for handler_class in handler_classes:
                if hasattr(handler_class, "msg_id"):
                    handlers[handler_class.msg_id] = handler_class()
        except Exception:
            executor.shutdown(wait=True, cancel_futures=True)
            logger.exception("Failed to register handlers")
            raise

        with cls._state_lock:
            cls._handlers = handlers
            cls._executor = executor
            cls._accepting = True
        logger.info("Registered %s handlers in total", len(handlers))

    @classmethod
    def process_packet(cls, msg_id: int, data: bytes, packet_id: int, session):
        """Process a packet, returning False when backpressure closes a session."""
        handler = cls._handlers.get(msg_id)
        if handler is None:
            logger.warning("No handler found for msg_id: %s", msg_id)
            cls._log_unknown_packet(msg_id, data)
            session.send(msg_id + 1, b"\x08\x02", packet_id, True)
            return True

        if msg_id in cls._SYNC_CMDS or msg_id in Config.DUNGEON_ORDERED_MESSAGE_IDS:
            with cls._state_lock:
                if not cls._accepting:
                    return False
            # 登录/有序链路保持在会话读线程内，避免同连接乱序。
            return cls._handle_packet(handler, session, data, packet_id, msg_id)

        with cls._state_lock:
            executor = cls._executor
            pending_bytes = cls._pending_bytes
            if (
                not cls._accepting
                or executor is None
                or len(cls._pending) >= cls.MAX_PENDING_PACKETS
                or pending_bytes + len(data) > cls.MAX_PENDING_BYTES
            ):
                rejected = True
            else:
                rejected = False
                try:
                    future = executor.submit(
                        cls._handle_packet, handler, session, data, packet_id, msg_id
                    )
                except RuntimeError:
                    rejected = True
                else:
                    cls._pending.add(future)
                    cls._pending_sizes[future] = len(data)
                    cls._pending_bytes += len(data)
                    future.add_done_callback(cls._packet_done)

        if rejected:
            logger.warning("Packet queue full; closing session %s", session.address)
            session.close()
            return False
        return True

    @classmethod
    def _packet_done(cls, future):
        with cls._state_lock:
            cls._pending.discard(future)
            cls._pending_bytes -= cls._pending_sizes.pop(future, 0)

    @classmethod
    def _handle_packet(cls, handler, session, data: bytes, packet_id: int, msg_id: int):
        try:
            if not session.running:
                return
            handler.handle(session, data, packet_id)
        except Exception:
            exception_traceback = traceback.format_exc()
            logger.error("Error processing %s packet: \n%s", msg_id, exception_traceback)
            cls._log_unknown_packet(msg_id, data)
            session.send(msg_id + 1, b"\x08\x02", packet_id, True)

    @classmethod
    def _log_unknown_packet(cls, msg_id: int, data: bytes):
        name = id_to_name.get(msg_id)
        if name:
            msg_class = getattr(net_pb2, name, None)
            if msg_class:
                try:
                    msg = msg_class()
                    msg.ParseFromString(data)
                    print(msg)
                except Exception:
                    pass

    @classmethod
    def shutdown(cls):
        """Stop accepting work and wait for all handlers before persistence."""
        with cls._state_lock:
            cls._accepting = False
            executor = cls._executor
            cls._executor = None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        with cls._state_lock:
            cls._pending.clear()
            cls._pending_sizes.clear()
            cls._pending_bytes = 0
            cls._handlers.clear()

    @classmethod
    def pending_count(cls):
        with cls._state_lock:
            return len(cls._pending)
