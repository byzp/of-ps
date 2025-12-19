class Config:
    # HTTP Server
    HTTP_HOST = "0.0.0.0"
    HTTP_PORT = 21000
    RES_VERSION = "2025-12-04-20-38-15_2025-12-19-18-26-58"
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

    REJECT_PAYMENT = False  # CreatePayOrderReq

    # database
    DB_PATH = "./player.db"
    IN_MEMORY = True

    # Package scanning
    HANDLERS_PACKAGE = "handlers"
