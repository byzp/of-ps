class Config:
    # CPython
    FORCE_DISABLE_GIL = False

    # HTTP Server
    HTTP_HOST = "0.0.0.0"
    HTTP_PORT = 21000
    RES_VERSION = "2025-09-19-16-44-33_2025-11-12-17-19-30"

    GAME_SERVER_GADGET_IP = "127.0.0.1"  # access
    GAME_SERVER_GADGET_PORT = 11033

    # Game Server
    GAME_SERVER_IP = "0.0.0.0"  # listen
    GAME_SERVER_PORT = 11033

    SESSION_POOL_MAX_WORKERS = 16
    SERVER_MAX_TPS = 120
    COMPRESS_THRESHOLD = 1200

    # database
    DB_PATH = "./player.db"
    IN_MEMORY = True

    # Package scanning
    HANDLERS_PACKAGE = "handlers"
