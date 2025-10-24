import logging
import threading
import time

from http_server.server import HTTPServer
from network.game_server import GameServer
import utils.res_loader as res_loader

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

    http_server = HTTPServer()
    http_thread = threading.Thread(target=http_server.start)
    http_thread.daemon = True
    http_thread.start()

    game_server = GameServer()
    game_server.start()


if __name__ == "__main__":
    main()
