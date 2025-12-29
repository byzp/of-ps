import logging
import threading
import sys

import http_server.server as http_server
from network.game_server import GameServer
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


def main():
    logger.info("OverFieldPS Start")

    # GIL
    if hasattr(sys, "_is_gil_enabled"):
        logger.info(f"GIL enabled: {sys._is_gil_enabled()}")
    else:
        logger.info(f"GIL enabled: True")

    stop_event = cmd.start()
    res_loader.init()
    db.init()

    http_thread = threading.Thread(target=http_server.start, daemon=True)
    http_thread.start()

    game_server = GameServer()
    game_server_thread = threading.Thread(target=game_server.start, daemon=True)
    game_server_thread.start()

    try:
        while not stop_event.is_set():
            stop_event.wait(0.1)
    except KeyboardInterrupt:
        stop_event.set()

    game_server.stop()

    logger.info("Exited cleanly")


if __name__ == "__main__":
    main()
