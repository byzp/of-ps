import logging
import signal
import sys
import threading

import http_server.server as http_server
from config import Config
from network.game_server import GameServer
import network.remote_link as remote_link
import server.notice_sync as notice_sync
import server.photo_share as photo_share
import utils.cmd as cmd
import utils.db as db
from utils import metrics as metrics_registry
import utils.res_loader as res_loader

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

_stop_once = threading.Event()
_shutdown_requested = threading.Event()


def _graceful_exit(signum, frame):
    """Signal handlers only request shutdown; persistence runs on the main path."""
    first = not _stop_once.is_set()
    _stop_once.set()
    _shutdown_requested.set()
    if first:
        logger.info("Shutdown requested by signal %s", signum)
    else:
        # Never os._exit here: a second Ctrl+C must not bypass an in-flight save.
        logger.warning("Shutdown already in progress; waiting for safe persistence")


def _shutdown_step(name, action):
    try:
        action()
    except Exception:
        logger.exception("Shutdown step failed: %s", name)
        return False
    return True


def main():
    _stop_once.clear()
    _shutdown_requested.clear()
    Config.validate()
    logger.info("OverFieldPS Start")
    logger.info(
        "config: HTTP=%s:%s GAME=%s:%s DISPATCH=%s:%s WORKERS=%s",
        Config.HTTP_HOST,
        Config.HTTP_PORT,
        Config.GAME_SERVER_IP,
        Config.GAME_SERVER_PORT,
        Config.GAME_SERVER_GADGET_IP,
        Config.GAME_SERVER_GADGET_PORT,
        Config.SESSION_POOL_MAX_WORKERS,
    )

    if hasattr(sys, "_is_gil_enabled"):
        logger.info(f"GIL enabled: {sys._is_gil_enabled()}")
    else:
        logger.info("GIL enabled: True")

    signal.signal(signal.SIGTERM, _graceful_exit)
    signal.signal(signal.SIGINT, _graceful_exit)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _graceful_exit)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _graceful_exit)

    stop_event = None
    http_thread = None
    game_server = None
    game_server_thread = None
    db_started = False
    photo_loaded = False
    shutdown_ok = True

    try:
        stop_event = cmd.start()
        res_loader.init()
        db_started = True
        db.init()

        photo_share.load()
        photo_loaded = True

        http_thread = threading.Thread(target=http_server.start, name="http-server", daemon=True)
        http_thread.start()

        game_server = GameServer()
        game_server_thread = threading.Thread(
            target=game_server.start, name="game-server", daemon=True
        )
        game_server_thread.start()

        if not game_server.wait_started(timeout=10.0):
            raise RuntimeError("Game server did not start")
        if not http_server.wait_started(timeout=5.0):
            raise RuntimeError(
                "HTTP server failed to start: " + str(http_server.startup_error())
            )

        if not stop_event.is_set() and not _shutdown_requested.is_set():
            remote_link.init()

        while not stop_event.is_set() and not _shutdown_requested.is_set():
            if not game_server.running:
                raise RuntimeError(
                    "Game server failed: " + str(game_server.startup_error)
                )
            if notice_sync.failed():
                raise RuntimeError("Notice sync failed")
            if http_server.startup_error():
                raise RuntimeError(
                    "HTTP server failed: " + str(http_server.startup_error())
                )
            stop_event.wait(0.1)
    except KeyboardInterrupt:
        if stop_event is not None:
            stop_event.set()
    finally:
        if stop_event is not None:
            stop_event.set()

        if game_server is not None:
            shutdown_ok &= _shutdown_step("game server", game_server.stop)
        shutdown_ok &= _shutdown_step("remote link", remote_link.stop)

        if http_thread is not None:
            shutdown_ok &= _shutdown_step("HTTP server", http_server.stop)
            http_thread.join(timeout=http_server.HTTP_GRACEFUL_SHUTDOWN + 2.0)
            if http_thread.is_alive():
                logger.error("HTTP server did not stop within its grace period")
                shutdown_ok = False
        if game_server_thread is not None:
            game_server_thread.join(timeout=6.0)
            if game_server_thread.is_alive():
                logger.error("Game server accept thread did not stop")
                shutdown_ok = False

        if photo_loaded:
            shutdown_ok &= _shutdown_step("photo share save", photo_share.save)
        if db_started:
            # db.exit() commits and closes synchronously; do not close the
            # database until all packet, notice and stamina workers have stopped.
            shutdown_ok &= _shutdown_step("database save", db.exit)

    if not shutdown_ok:
        raise RuntimeError("One or more shutdown steps failed")
    logger.info("metrics snapshot: %s", metrics_registry.metrics.snapshot())
    logger.info("Exited cleanly")


if __name__ == "__main__":
    main()
