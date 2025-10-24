import logging
import socket
import threading

from config import Config
from network.game_session import GameSession
from network.packet_factory import PacketFactory

logger = logging.getLogger(__name__)


class GameServer:
    def __init__(self, port: int = Config.GAME_SERVER_PORT):
        self.port = port
        self.server_socket = None

    def start(self):
        """Start the game server"""
        try:
            PacketFactory.initialize_handlers(Config.HANDLERS_PACKAGE)

            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", self.port))
            self.server_socket.listen(5)

            logger.info(f"Game server started on port {self.port}")

            while True:
                client_socket, address = self.server_socket.accept()
                logger.info(f"New connection from {address}")

                session = GameSession(client_socket)
                thread = threading.Thread(target=session.run)
                thread.daemon = True
                thread.start()

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
