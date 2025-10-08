import logging
from typing import Dict, Type
from network.packet_handler import PacketHandler
from utils.scanner import scan_handlers

logger = logging.getLogger(__name__)


class PacketFactory:
    _handlers: Dict[int, PacketHandler] = {}
    
    @classmethod
    def initialize_handlers(cls, package_name: str):
        """Scan and register all packet handlers"""
        try:
            handler_classes = scan_handlers(package_name)
            
            for handler_class in handler_classes:
                if hasattr(handler_class, 'cmd_id'):
                    instance = handler_class()
                    cls._handlers[handler_class.cmd_id] = instance
                    logger.debug(f"Registered handler for cmd_id: {handler_class.cmd_id}")
            
            logger.info(f"Registered {len(cls._handlers)} handlers in total")
            
        except Exception as e:
            logger.error(f"Failed to register handlers: {e}")
    
    @classmethod
    def process_packet(cls, cmd_id: int, data: bytes, session):
        """Process incoming packet"""
        handler = cls._handlers.get(cmd_id)
        if handler:
            try:
                handler.handle(session, data)
            except Exception as e:
                logger.error(f"Error processing packet: {e}")
        else:
            logger.warning(f"No handler found for cmd_id: {cmd_id}")