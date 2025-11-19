import logging
import threading
import signal

import http_server.server as http_server
from network.game_server import GameServer
import utils.res_loader as res_loader
import utils.cmd as cmd

res_loader.init()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    # filename='a.log',
    # filemode='w' # a
)

logger = logging.getLogger(__name__)


def main():
    logger.info("OverFieldPS Start")
    stop_event = cmd.start()

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
