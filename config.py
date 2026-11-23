from proto.net_pb2 import EArchaeologyType, EBagItemTag, LifeType, QuestStatus


class Config:
    # HTTP Server
    HTTP_HOST = "0.0.0.0"
    HTTP_PORT = 21000
    # RES_VERSION = "2026-10-21-14-05-50_2026-11-07-22-39-35" # cn
    RES_VERSION = "2026-10-24-12-00-58_2026-11-23-15-53-19"  # global
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
    SKIP_QUESTS = False

    # 活动秘境仅在窗口内显示。
    EVENT_DUNGEON_WINDOWS = {}

    # 特训任务类型与宝箱扣费模式。
    MATERIAL_DUNGEON_TYPE = 7
    DUNGEON_BOX_CONSUMPTION_MODE = 2
    DUNGEON_REWARD_MULTIPLIERS = (1, 2, 3)
    # 秘境 CoinInfos 收集点的固定奖励，官服 CollectCoinRsp 为106×1。
    DUNGEON_COIN_REWARD = (106, 1)
    # 副本生命周期请求按连接收包顺序执行：避免END/Finish/Exit互相抢跑。
    DUNGEON_ORDERED_MESSAGE_IDS = (1331, 1333, 1335, 1337, 1339, 1341, 1343, 1347, 1353)
    # 仅身处副本时串行的点位事件；世界中的击杀和开箱保持原分发方式。
    DUNGEON_POINT_MESSAGE_IDS = (1745, 1747, 1851)
    # 特训掉落数量按难度递增，封顶 6。
    DUNGEON_DROP_COUNTS_BY_TIER = (1, 2, 3, 4, 5, 6)

    # Link Server
    LINK_OTHER_SERVER = True
    SERVER_NAME = "aac"
    SELF_ADDR_IS_PUBLIC = False  # NAT 后设为 False
    LINK_LISTEN = ("0.0.0.0", 11000)
    SELF_ADDR = ("0.0.0.0", 11000)
    LINK_POOL = [
        ("139.196.113.128", 11000),
    ]
    LINK_POOL_CACHE = "./link_pool.json"

    # database
    DB_PATH = "./player.db"
    IN_MEMORY = True  # False=落盘；True=内存库+退出快照

    # Package scanning
    HANDLERS_PACKAGE = "handlers"

    PET_CATCH_RATES = [0.3, 0.5, 0.7, 1.0]

    # 学习动作有效期（秒）。
    ACTION_VALID_SECONDS = 86400

    ACTIVITY_BATTLE_PASS_BUY_EXP_FALLBACK_BUY = (102, 50, 1000)

    SANDBAG_MAX_HIT_PER_REQUEST = 100
    TURNTABLE_MAX_DRAW_TIMES = 10
    TURNTABLE_RECORD_PAGE_SIZE = 10

    # 游戏币物品 ID。
    GAME_COIN_ITEM_ID = 117
    BUY_GAME_COIN_FALLBACK_BUY = (102, 5, 1)
    GAME_COIN_MAX_FALLBACK = 6
    GAME_COIN_INITIAL_FALLBACK = 6
    GAME_COIN_RECOVER_SECONDS_FALLBACK = 10800

    # 角色升级允许消耗的经验道具物品 ID。
    CHARACTER_LEVEL_UP_ENERGY_ITEMS = (190, 191, 192)

    # 收集时即完成领奖(自动到账型)的图鉴类型
    COLLECTING_AUTO_REWARD_TYPES = (5, 8, 9)

    # 图鉴类型到带 reward_i_d 分表的映射。
    COLLECTION_REWARD_SHEETS = {
        1: "collection_item_file",
        2: "collection_item_item",
        3: "collection_item_book",
        6: "collection_item_data",
        9: "collect_item_photo_item",
    }

    WISH_STONE_ITEM_ID = 125

    DEFAULT_STAR_TIMERS = (200, 150, 100)

    EXPLORE_COLLECT_REWARD_COUNT = 5
    EXPLORE_REWARD_COUNT_PER_ITEM = 10

    FISHING_COST_ITEM_FALLBACK = 11
    FISHING_COST_COUNT_FALLBACK = 1

    # 生活类型到成就表的映射。
    GET_LIFE_ACHIEVE_LIFE_ITEM_FAMILIES = {
        2: ("Fishing", "fishing_info", "fish_achieve_rewards"),
        3: ("Make", "make_item", "make_achieve_rewards"),
        4: ("Handicraft", "handicraft_item", "handicraft_achieve_rewards"),
        5: ("Spin", "spin_item", "spin_achieve_rewards"),
        6: ("LifeGather", "life_gather_item", "life_gather_achieve_rewards"),
    }
    GET_LIFE_ACHIEVE_LIFE_TABLES = {
        1: ("Cooking", "cook_level", "cook_level_quest"),
        2: ("Fishing", "fishing_level", "fishing_level_quest"),
        3: ("Make", "make_level", "make_level_achieve"),
        4: ("Handicraft", "handicraft_level", "handicraft_level_achieve"),
        5: ("Spin", "spin_level", "spin_level_achieve"),
    }

    INTERVAL_SPEED_UP_MS_FALLBACK = 30 * 60 * 1000

    INVITE_CODE_REWARDS_FALLBACK = [(104, 1), (102, 30), (101, 5000)]

    VITALITY_ITEM_ID = 10
    # 每轮经验 = 体力 ×10。
    EXP_PER_VITALITY = 10

    # 生活等级表: life_type → (文件, 子表, 消耗字段前缀)
    LIFE_LEVE_UP_LEVEL_TABLES = {
        LifeType.LIFE_TYPE_Cooking: ("Cooking", "cook_level", "need_item"),
        LifeType.LIFE_TYPE_Fishing: ("Fishing", "fishing_level", "up_level_need_item"),
        LifeType.LIFE_TYPE_Making: ("Make", "make_level", "need_item"),
        LifeType.LIFE_TYPE_Handicraft: ("Handicraft", "handicraft_level", "need_item"),
        LifeType.LIFE_TYPE_Gathering: ("LifeGather", "life_gather", "need_item"),
    }

    # 生活技能表: life_type → (文件, 子表, 条目键, 等级键, 材料键)
    LIFE_SKILL_LEVEL_UP_SKILL_TABLES = {
        1: (
            "Cooking",
            "cook_spell",
            "cook_spell_items",
            "need_cook_level",
            "cook_need_item",
        ),
        2: (
            "Fishing",
            "fishing_spell",
            "fishing_spell_items",
            "need_fish_level",
            "fishing_need_item",
        ),
        3: (
            "Make",
            "make_spell",
            "make_spell_items",
            "need_make_level",
            "make_need_item",
        ),
        4: (
            "Handicraft",
            "handicraft_spell",
            "handicraft_spell_items",
            "need_handicraft_level",
            "handicraft_need_item",
        ),
        6: (
            "LifeGather",
            "life_gather_spell",
            "life_gather_spell_items",
            "need_gather_level",
            None,
        ),
    }

    MONTH_CARD_REWARD_FALLBACK = (102, 90)

    OPREATE_MAILS_INSTANCE_TAGS = (
        EBagItemTag.EBagItemTag_Weapon,
        EBagItemTag.EBagItemTag_Armor,
        EBagItemTag.EBagItemTag_Poster,
    )

    MAX_DYE_SCHEME_NUM = 16

    CAMPFIRE_NAMESPACE = "camp_fires"
    CAMPFIRE_TTL_MS = 3600 * 1000

    MOON_SPOT_NAMESPACE = "moon_spots"

    ENERGY_ITEM_ID = 11
    PLAYER_ENERGY_BUY_FALLBACK_TIER = (102, 30, 200)
    ENERGY_MAX_FALLBACK = 800

    PLAYER_VITALITY_BUY_FALLBACK_TIER = (102, 50, 60)
    VITALITY_MAX_FALLBACK = 150

    CHAT_HISTORY_MAX = 50
    PUBLIC_CHANNELS = (0, 1)

    SUPPLY_BOX_COIN_ITEM_ID = 101
    SUPPLY_BOX_COIN_COUNT = 1000

    # 教程场景宝箱只掉金币。
    TUTORIAL_SCENE_ID = 100
    TUTORIAL_BOX_COIN_ID = 101
    TUTORIAL_BOX_COIN_NUM = 100

    # 藏宝图到挖掘奖励池的映射。
    DIG_POOLS = {
        5070001: (7000030, 7000040, 7000050, 7000060),
        5070002: (7000080, 7000090, 7000100),
    }
    FAIL_POOL = 7000010

    TREASURE_ILLUSTRATION_INFO_ALL_TYPES = (
        EArchaeologyType.EArchaeologyType_Book,
        EArchaeologyType.EArchaeologyType_TreasureMap,
        EArchaeologyType.EArchaeologyType_Utensil,
        EArchaeologyType.EArchaeologyType_Furniture,
        EArchaeologyType.EArchaeologyType_Shovel,
    )

    # EArchaeologyType -> (资源文件, sheet)
    TREASURE_ILLUSTRATION_REWARD_TYPE_TABLES = {
        EArchaeologyType.EArchaeologyType_Book: ("Book", "book"),
        EArchaeologyType.EArchaeologyType_TreasureMap: ("Treasure", "treasure"),
        EArchaeologyType.EArchaeologyType_Utensil: ("Utensil", "utensil"),
        EArchaeologyType.EArchaeologyType_Furniture: ("Furniture", "furniture"),
        EArchaeologyType.EArchaeologyType_Shovel: ("Shovel", "shovel"),
    }

    # 允许更新的外观字段白名单。
    UPDATE_CHARACTER_APPEARANCE_FIELDS = [
        "badge",
        "umbrella_id",
        "insect_net_instance_id",
        "logging_axe_instance_id",
        "water_bottle_instance_id",
        "mining_hammer_instance_id",
        "collection_gloves_instance_id",
        "fishing_rod_instance_id",
        "vehicle_instance_id",
        "shovel_instance_id",
    ]

    # 探索收集子类型到成就条件类型。
    SUBTYPE_TO_TYPE = {
        "scenic": 11,
        "file": 12,  # 收集文件
        "collect": 13,  # 收集收藏品
        "book": 14,  # 收集书籍
        "tape": 15,  # 收集磁带
        "portal": 16,  # 激活传送点
        "data": 17,  # 收集资料
    }
    # 图鉴类型到收集子类型。
    COLL_TYPE_TO_SUB = {
        10: "crystal",
        1: "file",
        2: "collect",
        3: "book",
        4: "tape",
        5: "portal",
        6: "data",
        7: "photo",
    }
    # 收集子类型到星符成就类型。
    BADGE_SUB_TYPE = {
        "file": 91,
        "data": 92,
        "tape": 93,
        "book": 94,
        "crystal": 95,
        "scenic": 96,
        "photo": 97,
        "collect": 98,
    }
    # 考古图鉴类型到通用成就条件类型的映射。
    ARCHAEOLOGY_TYPE_TO_CONDITION = {
        0: 192,
        1: 188,
        2: 191,
        3: 190,
        4: 189,
    }
    # 按世界统计的成就条件类型到持久化计数键前缀的映射。
    ACHIEVE_TRACK_SCOPED_COUNTER_PREFIX = {
        3: "m3",
        11: "scenic",
        12: "file",
        13: "collect",
        14: "book",
        15: "tape",
        16: "portal",
        17: "data",
        91: "file",
        92: "data",
        93: "tape",
        94: "book",
        95: "crystal",
        96: "scenic",
        97: "photo",
        98: "collect",
        99: "m99",
        100: "portal",
        141: "portal",
        142: "scenic",
    }
    # 世界到场景组。
    WORLD_SCENES = {
        1: (1, 1000, 1001, 1002, 1003),
        2: (2,),
        3: (3,),
        4: (4,),
        5: (5,),
    }
    # 探索完成度包含的图鉴收集类型。
    EXPLORE_COLL_TYPES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
    # 采集产出物 id 前缀 -> (基础类型, 星符聚合类型, 世界计数子类)
    GATHER_PREFIX = {
        201: (61, 107, "g_plant"),  # 采集植物
        202: (62, 110, "g_wood"),  # 伐木
        203: (63, 109, "g_mine"),  # 挖矿
        204: (64, 108, "g_bug"),  # 捕虫
        205: (65, 111, "g_water"),  # 装水
        206: (66, None, None),  # 拾取
    }
    # 采集工具类型到成就条件类型。
    ACHIEVE_TRACK_GATHER_ACTION_TYPE = {
        4: 61,
        5: 62,
        6: 63,
        7: 64,
        8: 65,
        15: 66,
    }
    # 行为事件到成就计数操作的映射：(操作，条件类型，匹配字段，数量字段)。
    ACHIEVE_TRACK_EVENTS = {
        "kill": (
            ("add", 86, None, None),
            ("scoped", 106, None, None),
            ("add", 4, None, None),
            ("add", 6, None, None),
            ("add", 1, None, None),
        ),
        "gacha": (("add", 38, None, None),),
        "double_jump": (("add", 44, None, None),),
        "collect": (("add", 2, None, None),),
        "pickup": (("add", 72, None, None), ("add", 76, None, None)),
        "pet_capture": (("add", 70, None, None),),
        "cook": (
            ("add", 22, None, None),
            ("add", 168, None, None),
            ("add", 20, "recipe", None),
            ("add", 21, "tool", None),
        ),
        "cook_fail": (("add", 23, None, None),),
        "fish": (
            ("add", 26, None, None),
            ("add", 28, "fish", None),
            ("add", 30, "day", None),
            ("add", 31, "classify", None),
        ),
        "fish_fail": (("add", 27, None, None),),
        "craft_handmade": (("add", 46, None, None), ("add", 55, None, None)),
        "craft_furniture": (
            ("add", 47, None, None),
            ("add", 49, None, None),
            ("add", 56, None, None),
        ),
        "craft_sewing": (
            ("add", 48, None, None),
            ("add", 51, None, None),
            ("add", 57, None, None),
        ),
        "life_level": (("add", 24, None, None),),
        "treasure_box": (("add", 119, None, None), ("scoped", 3, None, None)),
        "dungeon_finish": (
            ("add", 6, None, None),
            ("add", 7, None, None),
            ("add", 32, None, None),
        ),
        "supply_box": (("add", 119, None, None), ("scoped", 3, None, None)),
        "encounter_done": (
            ("scoped", 103, None, None),
            ("add", 5, "scene", None),
            ("add", 4, None, None),
            ("add", 45, None, None),
            ("add", 115, None, None),
        ),
        "race_done": (("add", 18, None, None), ("scoped", 101, None, None)),
        "world_challenge_done": (("add", 19, None, None), ("scoped", 102, None, None)),
        "riddle_done": (("scoped", 105, None, None), ("add", 118, None, None)),
        "scene_enter": (("add", 39, None, None),),
        "channel_switch": (("add", 156, None, None),),
        "character_break": (("add", 90, None, None), ("add", 134, None, None)),
        "ability_level_up": (("add", 138, None, None),),
        "eat_food": (("add", 75, None, None),),
        "stamina_drink": (("add", 80, None, None),),
        "energy_drink": (("add", 81, None, None),),
        "vitality_restore": (("add", 146, None, None),),
        "energy_restore": (("add", 147, None, None),),
        "use_interact_item": (("add", 165, None, None),),
        "quest_complete": (("add", 136, None, None),),
        "social_action": (
            ("add", 165, None, None),
            ("add", 126, None, None),
            ("add", 130, None, None),
        ),
        "send_emoji": (("add", 74, None, None),),
        "wear_weapon": (("add", 145, None, None),),
        "wear_armor": (("add", 122, None, None),),
        "wear_poster": (("add", 155, None, None),),
        "skill_up": (
            ("add", 121, None, None),
            ("add", 157, None, None),
            ("add", 158, None, None),
        ),
        "sandbag_hit": (("add", 183, None, None),),
        "sandbag_day": (("add", 184, None, None),),
        "armor_enhance": (("add", 123, None, None), ("add", 149, None, None)),
        "weapon_enhance": (("add", 123, None, None), ("add", 151, None, None)),
        "disassemble": (
            ("add", 124, None, None),
            ("add", 148, None, "armor_n"),
            ("add", 150, None, "weapon_n"),
        ),
        "star_up": (("add", 120, None, None),),
        "badge_reward": (("add", 125, None, None),),
        "wear_outfit": (("add", 127, None, None),),
        "team_switch": (("add", 128, None, None),),
        "team_size": (("state", 135, "team_size", None),),
        "place_furniture": (("add", 129, None, None),),
        "character_dead": (("add", 131, None, None),),
        "change_umbrella": (("add", 144, None, None),),
        "appearance_change": (("add", 143, None, None),),
        "poster_starup": (("add", 160, None, None),),
        "poster_illustration_reward": (("add", 161, None, None),),
        "shop_collect_buy": (("add", 153, None, None),),
        "like_garden": (("add", 176, None, None),),
        "new_friend": (("add", 177, None, None),),
        "recall_player": (("add", 185, None, None),),
        "craft_furniture_process": (("add", 50, None, None),),
        "explore_reward": (("add", 84, None, None), ("add", 154, None, None)),
        "explore_collect_reward": (("add", 83, None, None),),
        "outfit_dye": (("add", 164, None, None),),
        "dungeon_rating": (("add", 58, None, None),),
        "area_unlock": (
            ("add", 139, None, None),
            ("scoped", 99, None, None),
            ("add", 43, "area_param", None),
        ),
        "area_level_up": (("add", 140, None, None),),
        # 中央归因(utils/item_mgr): 玩家等级状态 / 金币消耗 / 物品获得
        "player_level": (("state", 36, "level", None),),
        "character_level": (("state", 35, "level", None),),
        "spend_coin": (("add", 85, None, None),),
        "gain_item": (("add", 2, None, None), ("add", 44, None, None)),
    }
    ACHIEVE_TRACK_LIFE_LEARN_TYPE = {1: 24, 2: 29, 3: 53, 4: 52, 5: 54}
    ACHIEVE_TRACK_GATHER_CAT_SCOPED = {4: 107, 7: 108, 6: 109, 5: 110, 8: 111}

    # 连续中断信号确认退出的时间窗口，单位：秒。
    CMD_SIGINT_WINDOW = 10.0

    # 新号初始未开放的功能。
    INITIAL_UNLOCK_FUNCTIONS = ()
    INITIAL_QUEST_IDS = (910121, 910122, 910131, 910111, 900111, 900112, 900113, 910112)
    NEW_PLAYER_ITEMS = {
        2020: 10,
        8000: 1,
        116: 230,
        2073: 10,
        2074: 10,
        115: 140,
        5000: 1,
        2070: 10,
        11: 600,
        2071: 10,
        2072: 10,
        132: 1,
        4050: 1,
        10: 120,
        2050: 10,
    }
    # 当前区服配置查询。
    GENERIC_GAME_REGION_QUERY_ID = 6
    GENERIC_GAME_REGION_ID = 1003
    # 本区服可见招募池。
    GACHA_VISIBLE_IDS = (1000, 4000, 103005, 2000)
    # 本区服景点语音。
    SCENIC_VOICE_IDS = {1002: 101}
    # 教程完成后新增的功能。
    TUTORIAL_UNLOCK_FUNCTIONS = (
        100000009,
        100000003,
        100000006,
        100000021,
    )
    # 额外任务奖励与开放节点。
    QUEST_COMPLETION_EXTRA_ITEMS = {
        100088: ((100000044, 1),),
        101011: ((100000045, 1), (100000046, 1)),
    }
    # 完成第二章“进入世界”任务后激活场景支线及其入口旗标。
    QUEST_COMPLETION_START_QUESTS = {101012: (301011,)}
    # 每日祈愿任务的首次开放节点及对应功能；非 skip 模式登录按持久状态恢复。
    DAILY_TASK_UNLOCK_QUEST_ID = 101011
    DAILY_TASK_UNLOCK_FUNCTION_ID = 100000045
    # 区域装置首次激活奖励：初始空间的 101 不发放，开放世界装置均发放。
    AREA_UNLOCK_REWARDS = ((1, 300), (102, 10), (101, 1000))
    # 新手引导发放的功能解锁物品 ID。
    INITIAL_UNLOCK_ITEMS = (
        100000000,
        100000001,
        100000002,
        100000003,
        100000006,
        100000009,
        100000010,
        100000011,
        100000021,
        100000025,
        100000027,
        100000035,
        100000036,
        100000037,
        101000001,
        101000003,
    )
    BP_EXP_PER_LEVEL = 1000

    # 已解锁手册标记的持久化命名空间。
    MANUAL_FLAGS_NS = "manual_flags"
    # 已解锁场景标记的持久化命名空间。
    SCENE_FLAGS_NS = "scene_flags"

    DEFAULT_INTERVAL_ID = 103
    INTERVAL_DURATION_MS = 8 * 3600 * 1000
    DAILY_LIKE_LIMIT = 10

    TEMP_PACK_MAX = 30
    # 物品实例对应的 protobuf 字段名。
    ITEM_MGR_INSTANCE_FIELDS = ("weapon", "poster", "armor", "pet", "furniture")
    # 按实例管理的物品标签。
    ITEM_MGR_INSTANCE_TAGS = (2, 3, 5, 56, 34)
    # 角色卡物品标签。
    ITEM_MGR_CARD_TAG = 7

    # 生活类型到成就表。
    LIFE_ACHIEVE_LIFE_TABLES = {
        LifeType.LIFE_TYPE_Cooking: ("Cooking", "cook_level", "cook_level_quest"),
        LifeType.LIFE_TYPE_Fishing: ("Fishing", "fishing_level", "fishing_level_quest"),
        LifeType.LIFE_TYPE_Making: ("Make", "make_level", "make_level_achieve"),
        LifeType.LIFE_TYPE_Handicraft: (
            "Handicraft",
            "handicraft_level",
            "handicraft_level_achieve",
        ),
        LifeType.LIFE_TYPE_Sewing: ("Spin", "spin_level", "spin_level_achieve"),
    }
    # 生活类型到道具成就表。
    LIFE_ACHIEVE_LIFE_ITEM_FAMILIES = {
        1: ("Cooking", "cook_food", "cook_food_quest_rewards"),
        2: ("Fishing", "fishing_info", "fish_achieve_rewards"),
        3: ("Make", "make_item", "make_achieve_rewards"),
        4: ("Handicraft", "handicraft_item", "handicraft_achieve_rewards"),
        5: ("Spin", "spin_item", "spin_achieve_rewards"),
        6: ("LifeGather", "life_gather_item", "life_gather_achieve_rewards"),
    }

    INSTANCE_SCENE_TYPE = 2

    # 视为已完成的任务状态。
    QUEST_TRACK_DONE = (
        QuestStatus.QuestStatus_Completed,
        QuestStatus.QuestStatus_Finish,
    )

    # 排行榜最多返回的条目数。
    MAX_RANK_ENTRIES = 50

    # 每日结算的本地时间小时，范围为 0 至 23。
    DAY_RESET_HOUR = 4

    RESTAURANT_GAME_COIN_ITEM_ID = 1601
    RESTAURANT_GRID_COUNT_FALLBACK = 12

    NONE_REWARD = 999999999

    # 场景宝箱缺少刷新配置时的间隔，单位：秒；显式配置为 0 的一次性宝箱不使用此值。
    DEFAULT_SCENE_REFRESH_INTERVAL = 14400

    # 收藏类别对应 Level 表及等级条目；等级1起，按场景累计经验逐级扣除。
    COLLECTION_LEVEL_SHEETS = {
        1: "file_level",
        2: "collect_item_level",
        3: "book_level",
        4: "tape_level",
        5: "portal_level",
        6: "data_level",
        7: "photo_level",
        8: "crystal_level",
        9: "photo_item_level",
    }

    # 天气预报消息与窗口。
    WEATHER_FORECAST_MESSAGE_ID = 4
    WEATHER_FORECAST_HOURS = 12
    WEATHER_RAIN_HOURS = 2
    INITIAL_GAME_TIME_SECONDS = 21600
    GAME_DAY_REAL_SECONDS = 1800

    # 活动实例与奖励模板映射。
    ACTIVITY_INSTANCES = {
        1001: (0, 1001, 1762376400000, 0),
        260830103: (1, 2027, 1792684800000, 1793894399000),
        260830020: (4, 5075, 1793257200000, 1794412799000),
        260628074: (3, 10180, 1793462400000, 1796054399000),
        260730017: (6, 7005, 1792598400000, 1795017599000),
    }
    INACTIVE_ACTIVITY_IDS = (4002,)

    # 新号注册赠礼。
    NEW_PLAYER_MAIL_REWARDS = (
        ("20万预约庆贺礼", ((4100292, 1), (4100293, 1))),
        ("甜蜜贴贴、好礼送达", ((4645001, 1),)),
        ("预约奖励补发", ((125, 20),)),
    )
    # 教学对话完成时通过邮件发放首张映像：对话ID -> (邮件模板, 物品)。
    TUTORIAL_TALK_MAIL_REWARDS = {1000981: (14, ((11200, 1),))}
    # 未拾取的地面掉落在切场景时回收，模板2，有效期30天。
    LOST_DROP_MAIL_MODEL = 2
    LOST_DROP_MAIL_DAYS = 30

    # 普通怪掉落概率与数量。
    NORMAL_MONSTER_DROP_CHANCE = 0.2
    NORMAL_MONSTER_DROP_COUNT = (1, 2)
    NORMAL_MONSTER_DROP_WEIGHTS = ((2, 1), (3, 4), (8, 2))
    NORMAL_MONSTER_MATERIAL_COUNT = (1, 3)
    NORMAL_MONSTER_MATERIAL_SPIN_TYPE = 1
    SUPPLY_BOX_COOLDOWN_MINUTES = (10, 30)

    # 一次性箱固定奖励。
    TUTORIAL_BOX_REWARDS = {
        30001: (101, 10),
        3001: (101, 100),
        30002: (102, 10),
        3002: (101, 1000),
    }
    COLLECTION_BOX_REWARDS = {
        101005: (1102, 1),
        101007: (1101, 1),
        101008: (5041907, 1),
        101103: (4200203, 1),
    }
    # 普通箱本地掉落配置。
    NORMAL_BOX_CURRENCY = (101, 10)
    NORMAL_BOX_EQUIPMENT_COUNT = (1, 2)
    NORMAL_BOX_MATERIAL_IDS = (3004, 3005)
    NORMAL_BOX_MATERIAL_COUNT = (1, 3)
    NORMAL_BOX_MATERIAL_CHANCE = 0.5
    # 旗帜战结算生成的动态宝箱模板。
    BATTLE_TREASURE_BOX_ID = 300000
    # 收藏ID的地区段：00教学空间、99花园，其余直接对应世界场景。
    COLLECTION_REGION_SCENES = {0: 100, 99: 9999}
    # 这些条件仍使用通用计数，但通过Quest tracker展示，不发永久成就通知。
    ACHIEVE_TRACKER_FUNCTIONS = (3, 5, 10, 12, 14, 18, 19, 25, 32)
    # 本区服没有展示的通用事件tracker。
    HIDDEN_EVENT_TRACKERS = (20010011, 20010017)
    # 本区服活动可见实例；不混入客户端表残留的其他区服活动。
    ACTIVITY_VISIBLE_IDS = (
        1001,
        4008,
        260830020,
        2001,
        260830103,
        2003,
        3001,
        260628074,
        260730017,
    )
    # 推荐频道来自运营配置而非Chat静态分类；填写本服真实聊天室，默认无推荐。
    # 每项字段：channel_id、title、image_url、image_id。
    RECOMMENDED_CHAT_CHANNELS = ()
    # 场景状态广播与体力恢复轮询间隔，单位：现实秒。
    SCENE_STATE_SYNC_INTERVAL = 60.0
    STAMINA_SYNC_INTERVAL = 300
    # 已知战斗结算经验。
    BATTLE_CHARACTER_EXP = {
        ("encounter", 1073): 137,
        ("flag", 110300): 150,
        ("flag", 110220): 187,
        ("flag", 110230): 187,
    }
    # 祈愿击杀碎片奖励。
    MOON_KILL_REWARD_CHANCE = 1.0
    MOON_KILL_REWARD_POOL = 107
    MOON_KILL_REWARD_SOURCE_ID = 1101
    # 星云树节点奖励：(世界page, box_id) -> ((物品ID, 数量), ...)。
    BADGE_NODE_REWARDS = {
        1: {
            1: ((1002001, 1), (100000013, 1)),
            2: ((100000016, 1),),
            4: ((1003001, 1), (100000015, 1)),
            5: ((100000018, 1),),
            8: ((5041901, 1),),
            9: ((5041902, 1),),
            10: ((5041903, 1),),
            11: ((120010001, 1),),
            12: ((120010002, 1),),
            14: ((120010003, 1),),
            15: ((120010004, 1),),
            18: ((120010005, 1),),
            19: ((120010006, 1),),
            21: ((100002112, 1),),
            22: ((190, 20),),
            24: ((100002113, 1),),
            25: ((101, 800),),
            26: ((104, 1),),
            28: ((100002114, 1),),
            29: ((100002101, 1),),
            30: ((104, 1),),
            31: ((101000000, 1),),
            32: ((101000005, 1),),
            33: ((100000023, 1),),
            34: ((100001001, 1),),
            35: ((100001002, 1),),
            38: ((110010701, 1),),
            39: ((110010702, 1),),
            40: ((110010703, 1),),
        },
        2: {
            1: ((1004001, 1),),
            4: ((1001001, 1), (100000014, 1)),
            5: ((100000017, 1),),
            8: ((5042101, 1),),
            9: ((5042102, 1),),
            10: ((5042103, 1),),
            11: ((120020001, 1),),
            12: ((120020002, 1),),
            14: ((120020003, 1),),
            15: ((120020004, 1),),
            18: ((120020005, 1),),
            19: ((120020006, 1),),
            21: ((100002212, 1),),
            22: ((1000, 6), (1030, 6)),
            24: ((100002213, 1),),
            25: ((1010, 6), (1020, 6)),
            26: ((104, 1),),
            28: ((100002214, 1),),
            29: ((100002201, 1),),
            30: ((104, 1),),
            31: ((101000004, 1),),
            32: ((100001502, 1),),
            34: ((100001003, 1),),
            35: ((100001004, 1),),
            38: ((110020701, 1),),
            39: ((110020702, 1),),
            40: ((110020703, 1),),
        },
        3: {
            1: ((120030001, 1),),
            2: ((120030002, 1),),
            4: ((120030003, 1),),
            5: ((120030004, 1),),
            8: ((5041904, 1),),
            9: ((5041905, 1),),
            10: ((5041906, 1),),
            11: ((120030005, 1),),
            12: ((120030006, 1),),
            14: ((120030007, 1),),
            15: ((120030008, 1),),
            18: ((120030009, 1),),
            19: ((120030010, 1),),
            21: ((100002312, 1),),
            22: ((100002313, 1),),
            24: ((100002314, 1),),
            25: ((1011, 4), (1031, 4)),
            26: ((104, 1),),
            28: ((1021, 4), (1001, 4)),
            29: ((100002301, 1),),
            30: ((102, 100),),
            31: ((100001005, 1),),
            32: ((100001006, 1),),
            33: ((100001503, 1),),
            34: ((120030011, 1),),
            35: ((120030012, 1),),
            38: ((110031301, 1),),
            39: ((110031302, 1),),
            40: ((110031303, 1),),
        },
        4: {
            1: ((120040001, 1),),
            2: ((120040002, 1),),
            4: ((120040003, 1),),
            5: ((120040004, 1),),
            8: ((5042104, 1),),
            9: ((5042105, 1),),
            10: ((5042106, 1),),
            11: ((120040005, 1),),
            12: ((120040006, 1),),
            14: ((120040007, 1),),
            15: ((120040008, 1),),
            18: ((120040009, 1),),
            19: ((120040010, 1),),
            21: ((100002412, 1),),
            22: ((100002413, 1),),
            24: ((100002414, 1),),
            25: ((1022, 4), (1032, 4)),
            26: ((104, 1),),
            28: ((1002, 4), (1012, 4)),
            29: ((100002401, 1),),
            30: ((102, 100),),
            31: ((100001007, 1),),
            32: ((100001008, 1),),
            34: ((120040011, 1),),
            35: ((120040012, 1),),
            38: ((110041301, 1),),
            39: ((110041302, 1),),
            40: ((110041303, 1),),
        },
        5: {
            1: ((120050001, 1),),
            2: ((120050002, 1),),
            4: ((120050003, 1),),
            5: ((120050004, 1),),
            8: ((5043205, 1),),
            9: ((5043215, 1),),
            10: ((5043327, 1),),
            11: ((120050005, 1),),
            12: ((120050006, 1),),
            13: ((120050007, 1),),
            14: ((120050008, 1),),
            15: ((120050009, 1),),
            16: ((120050010, 1),),
            18: ((120050011, 1),),
            19: ((120050012, 1),),
            20: ((120050013, 1),),
            21: ((100002512, 1),),
            22: ((100002513, 1),),
            24: ((100002514, 1),),
            25: ((100002501, 1),),
            28: ((104, 1),),
            29: ((102, 100),),
            30: ((110, 1),),
            31: ((100001013, 1),),
            32: ((100001014, 1),),
            34: ((120050014, 1),),
            35: ((120050015, 1),),
            38: ((110051601, 1),),
            39: ((110051602, 1),),
            36: ((110051603, 1),),
        },
        1001: {
            1: ((120510001, 1),),
            2: ((120510002, 1),),
            3: ((5043102, 1),),
            4: ((120510003, 1),),
            5: ((120510004, 1),),
            6: ((5043103, 1),),
            8: ((5043104, 1),),
            11: ((120510005, 1),),
            12: ((120510006, 1),),
            14: ((120510007, 1),),
            15: ((120510008, 1),),
            18: ((120510009, 1),),
            19: ((120510010, 1),),
            21: ((100010112, 1),),
            22: ((100010113, 1),),
            23: ((102, 100),),
            24: ((100010114, 1),),
            25: ((100010101, 1),),
            28: ((104, 1),),
            31: ((100001009, 1),),
            32: ((100001010, 1),),
        },
        1002: {
            1: ((120520001, 1),),
            2: ((120520002, 1),),
            4: ((120520003, 1),),
            5: ((120520004, 1),),
            8: ((5043423, 1),),
            9: ((5043424, 1),),
            10: ((5043430, 1),),
            11: ((120520005, 1),),
            12: ((120520006, 1),),
            14: ((120520007, 1),),
            15: ((120520008, 1),),
            16: ((120520009, 1),),
            18: ((120520010, 1),),
            21: ((100010212, 1),),
            22: ((100010213, 1),),
            24: ((100010214, 1),),
            25: ((100010201, 1),),
            28: ((102, 100),),
            29: ((104, 1),),
            31: ((100001011, 1),),
            34: ((100001012, 1),),
            35: ((110521101, 1),),
        },
        1003: {
            1: ((5043911, 1),),
            2: ((5043912, 1),),
            4: ((5043913, 1),),
            11: ((120530001, 1),),
            12: ((120530002, 1),),
            14: ((120530003, 1),),
            15: ((120530004, 1),),
            21: ((102, 100),),
            22: ((104, 1),),
            31: ((110530501, 1),),
        },
    }
