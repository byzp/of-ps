import logging
import socket
from concurrent.futures import ThreadPoolExecutor

from config import Config
from network.game_session import GameSession
from network.packet_factory import PacketFactory
from server.scene_data import _session_list as session_list, lock_session
import server.notice_sync as notice_sync
from network.remote_link import sync_player

logger = logging.getLogger(__name__)


class GameServer:
    def __init__(self):
        self.port = Config.GAME_SERVER_PORT
        self.server_socket = None
        self.running = True
        self._session_pool = ThreadPoolExecutor(
            max_workers=Config.SESSION_POOL_MAX_WORKERS, thread_name_prefix="session"
        )

    def start(self):
        """Start the game server"""
        try:
            PacketFactory.initialize_handlers(Config.HANDLERS_PACKAGE)

            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:  # Linux
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass

            # 增大listen backlog
            self.server_socket.bind((Config.GAME_SERVER_IP, self.port))
            self.server_socket.listen(1024)
            self.server_socket.setblocking(True)
            logger.info(f"Game server started on port {self.port}")
            logger.info('For help, type "help"')
            notice_sync.init()

            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    client_socket.setblocking(True)

                    logger.debug(f"New connection from {address}")
                    session = GameSession(client_socket, address)

                    with lock_session:
                        session_list.append(session)
                    sync_player(session)
                    self._session_pool.submit(session.run)
                except OSError:
                    if self.running:
                        raise
                    break

        except Exception as e:
            logger.error(f"Failed to start server: {e}")

    def stop(self):
        self.running = False
        notice_sync.sync_stop = True
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass

        self._session_pool.shutdown(wait=False, cancel_futures=True)
