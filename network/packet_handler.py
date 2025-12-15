from abc import ABC, abstractmethod


class PacketHandler(ABC):
    __slots__ = ()

    @abstractmethod
    def handle(self, session, data: bytes, packet_id: int = 0):
        pass


def packet_handler(msg_id: int):
    """Decorator for registering packet handlers"""

    def decorator(cls):
        cls.msg_id = msg_id
        return cls

    return decorator
