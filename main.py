import logging
import threading

from http_server.server import HTTPServer
from network.game_server import GameServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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