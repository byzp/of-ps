from abc import ABC, abstractmethod

class PacketHandler(ABC):
    @abstractmethod
    def handle(self, session, data: bytes):
        pass


def packet_handler(cmd_id: int):
    """Decorator for registering packet handlers"""
    def decorator(cls):
        cls.cmd_id = cmd_id
        return cls
    return decorator