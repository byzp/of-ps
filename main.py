import logging
import threading
import signal

import http_server.server as http_server
from network.game_server import GameServer
import utils.res_loader as res_loader
import utils.command_handler as command_handler

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

    def _sig_handler(signum, frame):
        logging.info("Signal %s received, shutdown...")
        stop_event.set()

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

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
