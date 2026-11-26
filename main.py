import atexit
import logging
import signal
import threading
import os
import sys

import http_server.server as http_server
from config import Config
from network.game_server import GameServer
import network.remote_link as remote_link
import server.photo_share as photo_share
import utils.res_loader as res_loader
import utils.cmd as cmd
import utils.db as db

_LOG_FMT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

logging.basicConfig(level=logging.DEBUG, format=_LOG_FMT)
_root_logger = logging.getLogger()
# 控制台只打 INFO 以上, 全量 DEBUG 写文件(方便事后查问题)
for _h in list(_root_logger.handlers):
    _root_logger.removeHandler(_h)
_console_h = logging.StreamHandler(sys.stdout)
_console_h.setLevel(logging.INFO)
_console_h.setFormatter(logging.Formatter(_LOG_FMT))
_root_logger.addHandler(_console_h)
try:
    from logging.handlers import RotatingFileHandler

    _file_h = RotatingFileHandler(
        os.path.join(_LOG_DIR, "server.log"),
        maxBytes=32 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    _file_h.setLevel(logging.DEBUG)
    _file_h.setFormatter(logging.Formatter(_LOG_FMT))
    _root_logger.addHandler(_file_h)
except Exception:
    pass

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
    logger.info("config: DYE_NO_COST=%s DYE_STUFF_NUM=%s AUTOSAVE_INTERVAL_SEC=%s WORKERS=%s", getattr(Config, "DYE_NO_COST", None), getattr(Config, "DYE_STUFF_NUM", None), getattr(Config, "AUTOSAVE_INTERVAL_SEC", None), getattr(Config, "SESSION_POOL_MAX_WORKERS", None))

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

    # 自动提交线程：execute() 不 commit，靠它按「写条数/时间」落盘，
    # 避免进程被强杀时丢掉自启动以来的全部改动。
    autosave_stop = threading.Event()
    if Config.AUTOSAVE_INTERVAL_SEC > 0:
        threading.Thread(
            target=db.autosave_loop,
            args=(autosave_stop,),
            daemon=True,
            name="db-autosave",
        ).start()
        logger.info(
            f"autosave enabled: every {Config.AUTOSAVE_INTERVAL_SEC}s "
            f"or {Config.AUTOSAVE_MAX_DIRTY} writes"
        )

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

    autosave_stop.set()
    db.save()  # 退出前落盘(IN_MEMORY 模式回写磁盘快照)
    logger.info("Exited cleanly")


if __name__ == "__main__":
    main()
