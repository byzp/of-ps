class Config:
    # HTTP Server
    HTTP_HOST = "0.0.0.0"
    HTTP_PORT = 21000
    RES_VERSION = "2025-12-04-20-38-15_2025-12-26-18-44-23"
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
    DEBUG_PACKET_PASS = [1007, 1008, 1203, 1206, 2201, 2202]

    VERIFY_TOKEN = False
    REJECT_PAYMENT = False  # CreatePayOrderReq
    SKIP_QUESTS = True

    # Link Server
    LINK_OTHER_SERVER = True
    SERVER_NAME = "aac"
    SELF_ADDR_IS_PUBLIC = False  # Set to False if behind NAT (server will connect to others but won't advertise its address)
    LINK_LISTEN = ("0.0.0.0", 11000)
    SELF_ADDR = ("0.0.0.0", 11000)
    LINK_POOL = [
        ("139.196.113.128", 11000),
    ]
    LINK_POOL_CACHE = "./link_pool.json"

    # database
    DB_PATH = "./player.db"
    IN_MEMORY = True

    # Package scanning
    HANDLERS_PACKAGE = "handlers"
