class Config:
    # CPython
    FORCE_DISABLE_GIL = False

    # HTTP Server
    HTTP_HOST = "0.0.0.0"
    HTTP_PORT = 21000
    RES_VERSION = "2025-09-19-16-44-33_2025-11-26-18-01-35"
    RES_URL = "http://cdn-of.inutan.com/Resources;https://cdn-of.inutan.com/Resources;http://127.0.0.1:21000/Resources"

    GAME_SERVER_GADGET_IP = "127.0.0.1"  # access
    GAME_SERVER_GADGET_PORT = 11033

    # Game Server
    GAME_SERVER_IP = "0.0.0.0"  # listen
    GAME_SERVER_PORT = 11033

    SESSION_POOL_MAX_WORKERS = 4
    PACKET_POOL_MAX_WORKERS = 12
    SERVER_MAX_TPS = 120
    COMPRESS_THRESHOLD = 1200

    # database
    DB_PATH = "./player.db"
    IN_MEMORY = True

    # Package scanning
    HANDLERS_PACKAGE = "handlers"
