import atexit
import logging
import signal
import threading
import os
import sys

import http_server.server as http_server
from network.game_server import GameServer
import network.remote_link as remote_link
import server.photo_share as photo_share
import utils.res_loader as res_loader
import utils.cmd as cmd
import utils.db as db

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    # filename='a.log',
    # filemode='w' # a
)

logger = logging.getLogger(__name__)


_stop_once = threading.Event()


def _graceful_exit(signum, frame):
    # SIGTERM/SIGINT: 落盘一次后退出。
    if _stop_once.is_set():
        return
    _stop_once.set()
    try:
        db.exit()
    except Exception:
        logging.getLogger(__name__).exception("graceful save failed")
    logging.shutdown()
    os._exit(0)


def main():
    logger.info("OverFieldPS Start")

    # GIL
    if hasattr(sys, "_is_gil_enabled"):
        logger.info(f"GIL enabled: {sys._is_gil_enabled()}")
    else:
        logger.info(f"GIL enabled: True")

    atexit.register(db.exit)
    signal.signal(signal.SIGTERM, _graceful_exit)
    signal.signal(signal.SIGINT, _graceful_exit)
    # tmux 关闭会话/终端断开会发 SIGHUP, 同样必须落盘
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _graceful_exit)

    stop_event = cmd.start()
    res_loader.init()
    db.init()

    # 社交模块内存态持久化(照片墙/心愿单/SP密码等)
    photo_share.load()

    http_thread = threading.Thread(target=http_server.start, daemon=True)
    http_thread.start()

    game_server = GameServer()
    game_server_thread = threading.Thread(target=game_server.start, daemon=True)
    game_server_thread.start()

    remote_link.init()

    try:
        while not stop_event.is_set():
            stop_event.wait(0.1)
    except KeyboardInterrupt:
        stop_event.set()

    game_server.stop()

    db.save()  # 退出前落盘(IN_MEMORY 模式回写磁盘快照)
    logger.info("Exited cleanly")


if __name__ == "__main__":
    main()
