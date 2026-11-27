import logging
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

from config import Config
from network.game_session import GameSession
from network.packet_factory import PacketFactory
from server.scene_data import _session_list as session_list, lock_session
import server.notice_sync as notice_sync

logger = logging.getLogger(__name__)


class GameServer:
    MAX_CONNECTIONS = 512
    ACCEPT_TIMEOUT = 0.5

    def __init__(self):
        self.port = Config.GAME_SERVER_PORT
        self.server_socket = None
        self.running = False
        self.startup_error = None
        self.notice_thread = None
        self._started = Event()
        self._stopped = Event()
        self._stop_lock = Lock()
        self._session_pool = ThreadPoolExecutor(
            max_workers=Config.SESSION_POOL_MAX_WORKERS, thread_name_prefix="session"
        )

    def start(self):
        """Bind and serve until stop() is called.  Instances are single-use."""
        try:
            with self._stop_lock:
                if self._started.is_set() or self._stopped.is_set():
                    raise RuntimeError("GameServer instance cannot be started twice")
                PacketFactory.initialize_handlers(Config.HANDLERS_PACKAGE)
                self._discard_stale_sessions()

                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    # Windows SO_REUSEADDR can let a second process hijack a
                    # listening port.  Exclusive bind still releases cleanly
                    # when this listener and its accepted sockets are closed.
                    self.server_socket.setsockopt(
                        socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
                    )
                else:
                    self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Do not use SO_REUSEPORT: two processes must never silently
                # share a game port after an accidental double start.
                self.server_socket.settimeout(self.ACCEPT_TIMEOUT)
                self.server_socket.bind((Config.GAME_SERVER_IP, self.port))
                self.server_socket.listen(min(self.MAX_CONNECTIONS, 1024))
                self.server_socket.setblocking(True)
                # settimeout() is retained for accept; it does not make accepted
                # sockets blocking, so reset their mode explicitly.
                self.running = True
                logger.info("Game server started on port %s", self.server_socket.getsockname()[1])
                logger.info("For help, type 'help'")
                self.notice_thread = notice_sync.init()

            self._started.set()
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                except socket.timeout:
                    self._expire_queued_sessions()
                    continue
                except OSError:
                    if self.running:
                        raise
                    break

                if not self.running:
                    client_socket.close()
                    break
                client_socket.setblocking(True)
                logger.debug("New connection from %s", address)

                try:
                    session = GameSession(client_socket, address)
                except Exception:
                    logger.exception("Unable to initialize session from %s", address)
                    client_socket.close()
                    continue

                with lock_session:
                    local_count = sum(
                        1 for item in session_list if not getattr(item, "remote", False)
                    )
                    if local_count >= self.MAX_CONNECTIONS:
                        reject = True
                    else:
                        session_list.append(session)
                        reject = False
                if reject:
                    logger.warning("Connection limit reached; rejecting %s", address)
                    session.close()
                    continue

                try:
                    self._session_pool.submit(session.run)
                except RuntimeError:
                    with lock_session:
                        session_list[:] = [item for item in session_list if item is not session]
                    session.close()
                    if self.running:
                        raise
                    break
        except Exception as error:
            self.startup_error = str(error)
            self.running = False
            logger.exception("Failed to start server: %s", error)
            self._started.set()
            self.stop()
        finally:
            # Also releases wait_started() when stop races with startup.
            self._started.set()

    def _expire_queued_sessions(self):
        now = time.monotonic()
        with lock_session:
            expired = [
                session
                for session in session_list
                if not getattr(session, "remote", False)
                and not getattr(session, "run_started", False)
                and now - getattr(session, "created_at", now) >= GameSession.AUTH_TIMEOUT
            ]
            for session in expired:
                session_list[:] = [item for item in session_list if item is not session]
        for session in expired:
            logger.debug("Expiring queued session %s", session.address)
            session.close()

    def _discard_stale_sessions(self):
        with lock_session:
            stale = list(session_list)
            session_list.clear()
        for session in stale:
            try:
                session.close()
            except Exception:
                logger.exception("Unable to close stale session")

    def stop(self):
        """Idempotent, serialized shutdown; all owned workers finish before return."""
        with self._stop_lock:
            if self._stopped.is_set():
                return
            self.running = False
            self._started.set()
            first_error = None

            listener = self.server_socket
            self.server_socket = None
            if listener is not None:
                try:
                    listener.close()
                except OSError:
                    pass

            try:
                with lock_session:
                    sessions = list(session_list)
                for session in sessions:
                    try:
                        session.close()
                    except Exception:
                        logger.exception("Unable to close session")
            except Exception as error:
                first_error = error
                logger.exception("Session shutdown failed")

            try:
                self._session_pool.shutdown(wait=True, cancel_futures=True)
            except Exception as error:
                first_error = first_error or error
                logger.exception("Session pool shutdown failed")

            # No handler may write to the database after notice_sync performs
            # its final logout save.
            try:
                PacketFactory.shutdown()
            except Exception as error:
                first_error = first_error or error
                logger.exception("Packet pool shutdown failed")

            if self.notice_thread is not None:
                try:
                    notice_sync.stop()
                    self.notice_thread.join()
                except Exception as error:
                    first_error = first_error or error
                    logger.exception("Notice sync shutdown failed")

            try:
                with lock_session:
                    remaining = list(session_list)
                    session_list.clear()
                for session in remaining:
                    try:
                        session.close()
                    except Exception:
                        logger.exception("Unable to remove residual session")
            except Exception as error:
                first_error = first_error or error
                logger.exception("Session cleanup failed")
            finally:
                self._stopped.set()

            if first_error is not None:
                raise RuntimeError("GameServer shutdown completed with errors") from first_error

    def wait_started(self, timeout=None):
        if not self._started.wait(timeout):
            return False
        if self.startup_error:
            raise RuntimeError(self.startup_error)
        return self.running

    @property
    def stopped(self):
        return self._stopped.is_set()
