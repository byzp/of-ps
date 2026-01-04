import logging
from typing import Dict
from concurrent.futures import ThreadPoolExecutor
import traceback

from network.packet_handler import PacketHandler
from utils.scanner import scan_handlers
from network.msg_id import MsgId
from config import Config
from proto import OverField_pb2

logger = logging.getLogger(__name__)

id_to_name = {
    v: k
    for k, v in vars(MsgId).items()
    if not k.startswith("__") and isinstance(v, int)
}


class PacketFactory:
    _handlers: Dict[int, PacketHandler] = {}
    _executor: ThreadPoolExecutor = None

    # 需要同步处理的
    _SYNC_CMDS = frozenset((1001, 1003, 1005))

    @classmethod
    def initialize_handlers(cls, package_name: str):
        """Scan and register all packet handlers"""
        try:
            # 初始化线程池
            cls._executor = ThreadPoolExecutor(
                max_workers=Config.PACKET_POOL_MAX_WORKERS, thread_name_prefix="packet"
            )

            handler_classes = scan_handlers(package_name)

            for handler_class in handler_classes:
                if hasattr(handler_class, "msg_id"):
                    instance = handler_class()
                    cls._handlers[handler_class.msg_id] = instance
                    # logger.debug(f"Registered handler for msg_id: {handler_class.msg_id}")

            logger.info(f"Registered {len(cls._handlers)} handlers in total")

        except Exception as e:
            logger.error(f"Failed to register handlers: {e}")

    @classmethod
    def process_packet(cls, msg_id: int, data: bytes, packet_id: int, session):
        """Process incoming packet"""
        handler = cls._handlers.get(msg_id)

        if handler:
            if msg_id in cls._SYNC_CMDS:
                cls._handle_packet(handler, session, data, packet_id, msg_id)
            else:
                cls._executor.submit(
                    cls._handle_packet, handler, session, data, packet_id, msg_id
                )
        else:
            logger.warning(f"No handler found for msg_id: {msg_id}")
            cls._log_unknown_packet(msg_id, data)
            session.send(msg_id + 1, b"\x08\x02", packet_id, True)

    @classmethod
    def _handle_packet(cls, handler, session, data: bytes, packet_id: int, msg_id: int):
        try:
            handler.handle(session, data, packet_id)
        except Exception:
            exception_traceback = traceback.format_exc()
            logger.error(f"Error processing {msg_id} packet: \n{exception_traceback}")
            cls._log_unknown_packet(msg_id, data)
            session.send(msg_id + 1, b"\x08\x02", packet_id, True)

    @classmethod
    def _log_unknown_packet(cls, msg_id: int, data: bytes):
        name = id_to_name.get(msg_id)
        if name:
            msg_class = getattr(OverField_pb2, name, None)
            if msg_class:
                try:
                    msg = msg_class()
                    msg.ParseFromString(data)
                    print(msg)
                except Exception:
                    pass
