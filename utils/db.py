import datetime
import logging
import os
import pickle
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from config import Config
from proto.net_pb2 import (
    Character,
    EEquipType,
    EBagItemTag,
    ItemDetail,
    OutfitHideInfo,
    Quest,
    Achieve,
    QuestStatus,
    StatusCode,
    MailBriefData,
    LifeBaseInfo,
    Chapter,
    MailContentType,
    PBCollectionRewardData,
)
from utils import item_mgr as items_util
from utils import activity_state
from utils.pb_create import make_item, make_Quest
from utils.res_loader import res

logger = logging.getLogger(__name__)

conn = None
db = None
# RLock: SIGTERM 处理器与主线程同线程, 可能在已持锁处打断, 需可重入
lock_db = threading.RLock()


class db_result:
    """已脱离 SQLite 游标的查询结果，保留调用方使用的取值接口。"""

    __slots__ = ("_rows", "_position")

    def __init__(self, rows):
        self._rows = rows
        self._position = 0

    def fetchone(self):
        if self._position >= len(self._rows):
            return None
        row = self._rows[self._position]
        self._position += 1
        return row

    def fetchall(self):
        rows = self._rows[self._position :]
        self._position = len(self._rows)
        return rows


class db_warp:
    __slots__ = ("_conn", "_rw_lock", "_executor")

    def __init__(self, conn, max_workers=16):
        self._conn = conn
        self._rw_lock = lock_db
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def execute(self, *args, **kwargs):
        with self._rw_lock:
            # execute 后的取值和游标释放同样会访问共享连接，必须一并持锁。
            # 不向 handler 暴露原始游标，避免锁外 fetch 与其他线程的 SQL 并发。
            cur = self._conn.execute(*args, **kwargs)
            rows = cur.fetchall()
            cur.close()
            return db_result(rows)

    def execute_async(self, *args, **kwargs):
        return self._executor.submit(self.execute, *args, **kwargs)


def exit():
    global db, conn
    with lock_db:
        if conn is None:
            return  # 已关闭(幂等)
        conn.commit()
        if Config.IN_MEMORY:
            disk = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
            conn.backup(disk)
            disk.commit()
            disk.close()
        conn.close()
        conn = None
        db = None


def save():
    with lock_db:
        if conn is None:
            return  # 已关闭(幂等)
        conn.commit()
        if Config.IN_MEMORY:
            disk = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
            conn.backup(disk)
            disk.commit()


def init():
    # 初始化数据库连接,仅主线程调用,无需加锁
    if not os.path.exists(Config.DB_PATH):
        logger.warning("database not exists!")
    global db, conn
    if Config.IN_MEMORY:
        disk = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        disk.backup(conn)
        disk.close()
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = OFF;")
        conn.commit()
    else:
        conn = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.commit()

    db = db_warp(conn)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            user_token TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY,
            player_name TEXT,
            level INTEGER DEFAULT 10,
            exp INTEGER DEFAULT 200,
            sex INTEGER DEFAULT 0,
            world_level INTEGER DEFAULT 1,
            head INTEGER DEFAULT 41101,
            team_leader_badge INTEGER DEFAULT 5000,
            is_online INTEGER DEFAULT 0,
            sign TEXT DEFAULT '',
            guild_name TEXT DEFAULT '',
            character_id INTEGER DEFAULT 101001,
            garden_like_num INTEGER DEFAULT 0,
            register_time INTEGER,
            create_time INTEGER,
            region_name TEXT DEFAULT 'cn_prod_main',
            client_log_server_token TEXT DEFAULT '',
            server_time_zone INTEGER DEFAULT 28800,
            phone_background INTEGER DEFAULT 8000,
            birthday TEXT DEFAULT '1992-02-25',
            is_hide_birthday INTEGER DEFAULT 0,
            hide_value INTEGER DEFAULT 0,
            account_type INTEGER DEFAULT 9999,
            unlock_functions BLOB,
            team BLOB,
            avatar_frame INTEGER DEFAULT 0,
            pendant INTEGER DEFAULT 0,
            pet_instance_id INTEGER DEFAULT 0,
            last_login_time INTEGER DEFAULT 1700000000000
        );

        CREATE TABLE IF NOT EXISTS characters (
            player_id INTEGER NOT NULL,
            character_id INTEGER NOT NULL,
            character_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, character_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS items (
            player_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            item_detail_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, item_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS items_s (
            player_id INTEGER NOT NULL,
            instance_id INTEGER NOT NULL,
            item_detail_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, instance_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS quests (
            player_id INTEGER NOT NULL,
            quest_id INTEGER NOT NULL,
            quest_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, quest_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS chapters (
            player_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            chapter_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, chapter_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS treasure_box (
            player_id INTEGER NOT NULL,
            box_id INTEGER NOT NULL,
            box_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, box_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS month_card (
            player_id INTEGER PRIMARY KEY,
            over_due_time INTEGER DEFAULT 0,
            reward_days INTEGER DEFAULT 0,
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );
         
        CREATE TABLE IF NOT EXISTS garden_info (
            player_id INTEGER PRIMARY KEY,
            like_num INTEGER DEFAULT 0,
            access_num INTEGER DEFAULT 0,
            furniture_num INTEGER DEFAULT 0,
            furniture_limit_num INTEGER DEFAULT 50000,
            is_open INTEGER DEFAULT 1,
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS life_info (
            player_id INTEGER PRIMARY KEY,
            life_blob BLOB NOT NULL,
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS mail (
            player_id INTEGER NOT NULL,
            mail_id INTEGER NOT NULL,
            mail_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, mail_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS friend (
            player_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            friend_status INTEGER DEFAULT 0,
            alias TEXT DEFAULT '',
            friend_tag INTEGER DEFAULT 0,
            friend_intimacy INTEGER DEFAULT 0,
            friend_background INTEGER DEFAULT 0,
            PRIMARY KEY (player_id, friend_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE,
            FOREIGN KEY(friend_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS achieve (
            player_id INTEGER NOT NULL,
            achieve_id INTEGER NOT NULL,
            achieve_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, achieve_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE,
            FOREIGN KEY(achieve_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS instance (
            player_id INTEGER NOT NULL,
            instance_id INTEGER NOT NULL,
            PRIMARY KEY (player_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bless_tree (
            player_id INTEGER NOT NULL,
            def_id INTEGER NOT NULL,
            tree_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, def_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ability_tree (
            player_id INTEGER NOT NULL,
            scene_id INTEGER NOT NULL,
            tree_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, scene_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS collections (
            player_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            collection_type INTEGER NOT NULL,
            item_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, item_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS gacha_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            gacha_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            gacha_time INTEGER NOT NULL,
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS gacha_guarantee (
            player_id INTEGER NOT NULL,
            gacha_id INTEGER NOT NULL,
            guarantee INTEGER DEFAULT 0,
            PRIMARY KEY (player_id, gacha_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS furnitures (
            scene_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            furniture_id INTEGER NOT NULL,
            furniture_detail_blob BLOB NOT NULL,
            PRIMARY KEY (scene_id, channel_id, player_id, furniture_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS areas (
            player_id INTEGER NOT NULL,
            scene_id INTEGER NOT NULL,
            area_id INTEGER NOT NULL,
            area_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, scene_id, area_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS challenges (
            player_id INTEGER NOT NULL,
            scene_id INTEGER NOT NULL,
            challenge_id INTEGER NOT NULL,
            challenge_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, scene_id, challenge_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS dungeons (
            player_id INTEGER NOT NULL,
            dungeon_id INTEGER NOT NULL,
            dungeon_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, dungeon_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS boss_rush_info (
            player_id INTEGER NOT NULL,
            season_id INTEGER NOT NULL,
            info_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, season_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS player_kv (
            player_id INTEGER NOT NULL,
            ns TEXT NOT NULL,
            k TEXT NOT NULL,
            v BLOB,
            PRIMARY KEY (player_id, ns, k),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS claimed_rewards (
            player_id INTEGER NOT NULL,
            system TEXT NOT NULL,
            key TEXT NOT NULL,
            claim_time INTEGER DEFAULT 0,
            PRIMARY KEY (player_id, system, key),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS photo_shares (
            share_code TEXT PRIMARY KEY,
            player_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            data_blob BLOB,
            likes INTEGER DEFAULT 0,
            create_time INTEGER DEFAULT 0,
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            code_type TEXT DEFAULT 'redeem',
            rewards TEXT DEFAULT '',
            max_uses INTEGER DEFAULT 0,
            used INTEGER DEFAULT 0,
            expire_time INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS redeem_code_uses (
            code TEXT NOT NULL,
            player_id INTEGER NOT NULL,
            use_time INTEGER DEFAULT 0,
            PRIMARY KEY (code, player_id)
        );

        CREATE TABLE IF NOT EXISTS turntable_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            activity_id INTEGER NOT NULL,
            "index" INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            item_num INTEGER NOT NULL,
            draw_time INTEGER NOT NULL,
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        INSERT OR IGNORE INTO users (id, username, password, user_token) VALUES (1000000, "", "", "");
    """)


def _quest_trackers(player_id):
    """任务追踪条目始终由资源配置及通用成就计数生成。"""
    return [
        quest.SerializeToString() for quest in activity_state.quest_trackers(player_id)
    ]


def init_player(player_id):
    """初始化新用户数据"""
    cur_time = int(time.time())
    player_name = ""
    player_unlock_data = (
        res.get("PlayerUnlock", {}).get("player_unlock", {}).get("datas", [])
    )
    all_unlock_func_ids = [item["i_d"] for item in player_unlock_data]
    unlock_func_ids = (
        all_unlock_func_ids
        if Config.SKIP_QUESTS
        else list(Config.INITIAL_UNLOCK_FUNCTIONS)
    )
    unlock_funcs = pickle.dumps(unlock_func_ids)

    team = pickle.dumps((101001, 0, 0))

    db.execute(
        """INSERT OR IGNORE INTO players
        (player_id, player_name, register_time, create_time, unlock_functions, team, level, exp, last_login_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            player_id,
            player_name,
            cur_time,
            cur_time,
            unlock_funcs,
            team,
            1 if not Config.SKIP_QUESTS else 10,
            0 if not Config.SKIP_QUESTS else 200,
            cur_time * 1000,
        ),
    )
    """
    # 初始化月卡
    db.execute(
        "INSERT OR IGNORE INTO month_card (player_id, over_due_time, reward_days) VALUES (?, ?, ?)",
        (player_id, 1744664399, 3),
    )
    """
    # 初始化花园
    db.execute("INSERT OR IGNORE INTO garden_info (player_id) VALUES (?)", (player_id,))

    # 初始化角色
    add_character(player_id, 101001)

    # 初始化必要物品
    initial_items = (
        {
            10: 150,
            11: 800,
            101: 500,
            102: 200,
            104: 1,
            5012011: 4,  # 鸡蛋拌饭原材料, 主线第一章第八话
            5011001: 6,
            5011018: 5,
        }
        if Config.SKIP_QUESTS
        else Config.NEW_PLAYER_ITEMS
    )
    for k, v in initial_items.items():
        item = make_item(k, v)

        set_item_detail(player_id, item.SerializeToString(), k)

    # 初始化 Achieve
    for achieve in res["Achieve"]["achieve"]["datas"]:
        if achieve.get("i_d", 0):
            tmp = Achieve()
            tmp.achieve_id = achieve["i_d"]
            set_achieve(player_id, achieve["i_d"], tmp.SerializeToString())

    # 跳过任务
    if Config.SKIP_QUESTS:
        for quest in res["Quest"]["quest"]["datas"]:
            tmp = Quest()
            tmp.quest_id = quest["i_d"]
            if quest.get("condition_set_group_i_d", 0):
                for condition in res["Quest"]["condition_set_group"]["datas"]:
                    if condition["i_d"] == quest["condition_set_group_i_d"]:
                        for condition_set in condition["quest_condition_set"]:
                            for achieve_condition_id in condition_set[
                                "achieve_condition_i_d"
                            ]:
                                tmp1 = tmp.conditions.add()
                                tmp1.condition_id = achieve_condition_id
                                # for achieve in res["Achieve"]["achieve"]["datas"]:
                                # if achieve["i_d"] == achieve_condition_id:
                                tmp1.status = QuestStatus.QuestStatus_Finish
                        break
            tmp.status = QuestStatus.QuestStatus_Finish
            tmp.bonus_times = 1
            set_quest(player_id, quest["i_d"], tmp.SerializeToString())
    else:
        # 登录包已包含八个教学任务；正式主线100011仍在离开初始空间后接取。
        for quest_id in Config.INITIAL_QUEST_IDS:
            quest = make_Quest(player_id, quest_id)
            set_quest(player_id, quest_id, quest.SerializeToString())

    # 初始化任务章节
    for chapter in res["Story"]["story_chapter"]["datas"]:
        tmp = Chapter()
        tmp.chapter_id = chapter["i_d"]
        if Config.SKIP_QUESTS:
            for story in chapter["story_list"]:
                tmp.rewarded_story_ids.append(story)
            set_chapter(player_id, chapter["i_d"], tmp.SerializeToString())
        # 对齐模式: 章节剧情均未领取, 由 ClaimQuestReward 按需创建
    # 初始化生活信息
    life_list = {}
    for i in range(1, 7):
        tmp = LifeBaseInfo()
        tmp.life_type = i
        tmp.level = 1
        life_list[i] = tmp.SerializeToString()
    db.execute(
        f"INSERT OR REPLACE INTO life_info (player_id, life_blob) VALUES (?, ?)",
        (player_id, pickle.dumps(life_list)),
    )
    # 初始化祈愿树
    for tree in res["BlessingTree"]["blessing_tree_info"]["datas"]:
        tree_id = []
        set_bless_tree(player_id, tree["i_d"], tree_id)
    # 初始化空间收集物, 没有就是未收集

    # 一封欢迎邮件
    mail = MailBriefData()
    mail.mail_id = 1
    mail.sender = "aac"
    mail.content_type = MailContentType.MailContentType_TEXT
    mail.send_time = int(time.time())
    mail.title = "of-ps"
    mail.content = 'This project is open source under the AGPL. Repository: <color=#66ccff><b><link="https://github.com/byzp/of-ps">https://github.com/byzp/of-ps</link></b></color>. If you find it useful, please give it a star.\n\n'
    mail.overdue_day = 3650
    tmp = mail.items.add()
    tmp.item_id = 108
    tmp.num = 1488891
    set_mail(player_id, 1, mail.SerializeToString())


def verify_sdk_user_info(user_id, login_token):
    cur = db.execute(
        "SELECT id, username, user_token FROM users WHERE id = ? AND user_token = ?",
        (
            user_id,
            login_token,
        ),
    )
    row = cur.fetchone()
    if row:
        return True
    return False


def get_sdk_user_info(username, password):

    cur = db.execute(
        "SELECT id, password, user_token FROM users WHERE username = ?",
        (username,),
    )
    row = cur.fetchone()
    if row:
        if row[1] == password:
            return {"id": row[0], "username": username, "user_token": row[2]}
        else:
            return None
    else:

        auth_token = secrets.token_hex(16)
        cur = db.execute(
            "INSERT INTO users (username, password, user_token) VALUES (?, ?, ?)",
            (username, password, auth_token),
        )
        return {
            "id": get_sdk_user_info(username, password)["id"],
            "username": username,
            "user_token": auth_token,
        }


def get_user_id(sdk_id):
    return sdk_id


def get_player_id(user_id):
    cur = db.execute("SELECT player_id FROM players WHERE player_id=?;", (user_id,))
    row = cur.fetchone()

    if row is None:
        init_player(user_id)

    return user_id


def get_players_info(player_index, info_name):
    """获取玩家信息"""
    if isinstance(player_index, int):
        cur = db.execute(
            f"SELECT {info_name} FROM players WHERE player_id=?", (player_index,)
        )
    else:
        cur = db.execute(
            f"SELECT {info_name} FROM players WHERE player_name=?", (player_index,)
        )
    row = cur.fetchone()
    if row:
        infos = []
        # 如果是BLOB类型字段，需要反序列化
        blob_fields = ["team", "unlock_functions"]
        info_fields = info_name.split(",")
        for i, info in enumerate(info_fields):
            if info in blob_fields:
                infos.append(pickle.loads(row[i]))
            else:
                infos.append(row[i])
        return infos


def get_unlock_functions(player_id):
    """返回玩家已开启的功能 id 列表。"""
    row = get_players_info(player_id, "unlock_functions")
    if not row or row[0] is None:
        return []
    functions = row[0]
    if not isinstance(functions, (list, tuple, set)):
        raise TypeError("unlock_functions must be a sequence")
    return list(dict.fromkeys(functions))


def has_unlock_function(player_id, function_id):
    """判断玩家是否已开启指定功能。"""
    return function_id in get_unlock_functions(player_id)


def function_unlocked(player_id, function_id):
    """判断功能是否可用；skip 模式保留旧行为，视为全部开放。"""
    return Config.SKIP_QUESTS or has_unlock_function(player_id, function_id)


def require_function(session, rsp, msg_id, packet_id, function_id):
    """检查功能解锁状态并发送统一的未解锁响应。

    返回 True 表示可以继续处理；返回 False 时调用方必须立即 return。
    将门禁放在请求处理最前面，避免新手阶段提前写入功能状态或消耗资源。
    """
    if function_unlocked(session.player_id, function_id):
        return True

    rsp.status = StatusCode.StatusCode_FunctionUnlock
    session.send(msg_id, rsp, packet_id)
    return False


def add_unlock_functions(player_id, function_ids):
    """幂等加入功能并返回本次首次加入的 id。"""
    current = get_unlock_functions(player_id)
    known = set(current)
    added = []
    for function_id in function_ids:
        if not function_id or function_id in known:
            continue
        known.add(function_id)
        current.append(function_id)
        added.append(function_id)
    if added:
        set_players_info(player_id, "unlock_functions", current)
    return added


def get_player_name_exists(player_name):
    """检查数据库中是否已存在相同的玩家昵称"""
    cur = db.execute("SELECT COUNT(*) FROM players WHERE player_name=?", (player_name,))
    row = cur.fetchone()
    return row[0] > 0


def set_players_info(player_id, info_name, value):
    """设置玩家信息"""
    if info_name in ["team", "unlock_functions"]:
        value = pickle.dumps(value)
    db.execute(
        f"UPDATE players SET {info_name}=? WHERE player_id=?", (value, player_id)
    )


def get_register_time(player_id):
    cur = db.execute(
        "SELECT register_time FROM players WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return int(row[0] if row else int(time.time()))


def get_analysis_account_id(player_id):
    return str(player_id)


def get_SupplyBox_next_reward_time(player_id):
    cur = db.execute(
        "SELECT next_reward_time FROM supply_box WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return row[0] if row else int(time.time() + 3600)


def set_SupplyBox_next_reward_time(player_id, next_time):
    db.execute(
        "INSERT OR REPLACE INTO supply_box (player_id, next_reward_time) VALUES (?, ?)",
        (player_id, next_time),
    )


def get_garden_info(player_id):
    cur = db.execute(
        "SELECT like_num, access_num, furniture_num, furniture_limit_num, is_open FROM garden_info WHERE player_id=?",
        (player_id,),
    )
    row = cur.fetchone()
    if row:
        return row[0], row[1], row[2], row[3], bool(row[4])
    return 0, 0, 0, 500000, True


def set_garden_info(
    player_id, like_num, access_num, furniture_num, furniture_limit_num, is_open
):
    db.execute(
        """INSERT OR REPLACE INTO garden_info 
        (player_id, like_num, access_num, furniture_num, furniture_limit_num, is_open) VALUES (?, ?, ?, ?, ?, ?)""",
        (
            player_id,
            like_num,
            access_num,
            furniture_num,
            furniture_limit_num,
            int(is_open),
        ),
    )


def get_characters(player_id, character_id=None) -> list:
    """获取玩家角色信息"""
    chrs = []
    if character_id:
        cur = db.execute(
            "SELECT character_blob FROM characters WHERE player_id=? AND character_id=?",
            (player_id, character_id),
        )
        row = cur.fetchone()
        if row:
            chrs.append(row[0])
        return chrs

    else:
        cur = db.execute(
            "SELECT character_blob FROM characters WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        for row in rows:
            chrs.append(row[0])
        return chrs


def set_character(player_id, character_id, character_blob):
    """更新玩家角色信息"""

    db.execute(
        "INSERT OR REPLACE INTO characters (player_id, character_id, character_blob) VALUES (?, ?, ?)",
        (player_id, character_id, character_blob),
    )


def get_item_detail(player_id, item_id=None, instance_id=None, table=None) -> list:
    """
    获取物品详情
    :param player_id: 玩家ID
    :param item_id: 物品ID（可选）
    :param instance_id: 实例ID（可选）
    :param table: 表名（"items" 或 "items_s"，默认为None表示两个表都查）
    :return: 物品详情列表或单个物品详情
    """
    if item_id:
        cur = db.execute(
            "SELECT item_detail_blob FROM items WHERE player_id=? AND item_id=?",
            (player_id, item_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    if instance_id:
        cur = db.execute(
            "SELECT item_detail_blob FROM items_s WHERE player_id=? AND instance_id=?",
            (player_id, instance_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    if table == "items":
        items = []
        cur = db.execute(
            "SELECT item_detail_blob FROM items WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                items.append(row[0])
        return items

    if table == "items_s":
        items = []
        cur = db.execute(
            "SELECT item_detail_blob FROM items_s WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                items.append(row[0])
        return items

    if not item_id and not instance_id:
        items = []
        cur = db.execute(
            "SELECT item_detail_blob FROM items WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                items.append(row[0])

        cur = db.execute(
            "SELECT item_detail_blob FROM items_s WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                items.append(row[0])
        return items


def set_item_detail(player_id, item_detail_blob, item_id=None, instance_id=None):
    # is_new是本次获得的提示，不是背包持久状态；更新/扣除/登录不得重放。
    detail = ItemDetail.FromString(item_detail_blob)
    which = detail.main_item.WhichOneof("item")
    if (
        detail.main_item.item_id
        and which is not None
        and (which != "base_item" or detail.main_item.base_item.num > 0)
    ):
        try_claim(player_id, "got_ids", detail.main_item.item_id)
    detail.main_item.is_new = False
    item_detail_blob = detail.SerializeToString()
    if item_id:
        db.execute(
            "INSERT OR REPLACE INTO items (player_id, item_id, item_detail_blob) VALUES (?, ?, ?)",
            (player_id, item_id, item_detail_blob),
        )
    if instance_id:
        db.execute(
            "INSERT OR REPLACE INTO items_s (player_id, instance_id, item_detail_blob) VALUES (?, ?, ?)",
            (player_id, instance_id, item_detail_blob),
        )


def del_item_detail(
    player_id,
    instance_id,
):
    db.execute(
        "DELETE FROM items_s WHERE player_id=? AND instance_id=?",
        (
            player_id,
            instance_id,
        ),
    )


def get_month_card_over_due_time(player_id):
    cur = db.execute(
        "SELECT over_due_time FROM month_card WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return row[0] if row else 0


def set_month_card_over_due_time(player_id, over_due_time):
    db.execute(
        "INSERT OR REPLACE INTO month_card (player_id, over_due_time) VALUES (?, ?)",
        (player_id, over_due_time),
    )


def get_month_card_reward_days(player_id):
    cur = db.execute(
        "SELECT reward_days FROM month_card WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return row[0] if row else 0


def set_month_card_reward_days(player_id, reward_days):
    db.execute(
        "UPDATE month_card SET reward_days=? WHERE player_id=?",
        (reward_days, player_id),
    )


def get_chat_history(player_id):
    """公共频道聊天记录(kv player_id=0, 由 SendChatMsg 写入);
    无记录的频道返回空 msg, 上层不下发初始化包。"""

    result = []
    for chat_type in (0, 1, 2, 3):
        raw = get_kv(0, "chat_history", str(chat_type), b"")
        msgs = []
        if raw:
            msgs = pickle.loads(raw)
        result.append({"type": chat_type, "msg": msgs})
    return result


def add_chat_message(player_id, chat_type, message):
    """添加聊天消息"""
    history = get_chat_history(player_id)

    # 找到对应类型的聊天记录
    for chat in history:
        if chat["type"] == chat_type:
            chat["msg"].append(message)
            break

    db.execute(
        "UPDATE chat_history SET history_data=? WHERE player_id=?",
        (pickle.dumps(history), player_id),
    )


def get_character_achievement_lst(player_id, chr_id):
    for i in res["Character"]["character_achieve"]["datas"]:
        if i["i_d"] == chr_id:
            return i["achieve_info"]
    return None


def set_character_equip(player_id, chr_id, equipment_preset):
    """更新角色装备"""
    db.execute(
        """INSERT OR REPLACE INTO character_equip 
        (player_id, character_id, equipment_preset) VALUES (?, ?, ?)""",
        (player_id, chr_id, pickle.dumps(equipment_preset)),
    )


def get_character_equip(player_id, chr_id):
    """获取角色装备"""
    cur = db.execute(
        "SELECT equipment_preset FROM character_equip WHERE player_id=? AND character_id=?",
        (player_id, chr_id),
    )
    row = cur.fetchone()
    if row and row[0]:
        return pickle.loads(row[0])
    return None


def get_friend_info(player_id, friend_id=None, info_name="*"):
    """获取好友信息"""
    if friend_id:
        cur = db.execute(
            f"SELECT {info_name} FROM friend WHERE player_id=? AND friend_id=?",
            (player_id, friend_id),
        )
        row = cur.fetchone()
        if row:
            return row
        return [None]
    else:
        cur = db.execute(
            f"SELECT {info_name} FROM friend WHERE player_id=?",
            (player_id,),
        )
        friends = []
        rows = cur.fetchall()
        if rows:
            for row in rows:
                friends.append(row)
        return friends


def set_friend_info(player_id, friend_id, info_name, value):
    """设置好友信息"""
    db.execute(
        f"UPDATE friend SET {info_name}=? WHERE player_id=? AND friend_id=?",
        (value, player_id, friend_id),
    )


def init_friend(player_id, friend_id):
    """初始化好友关系"""
    db.execute(
        "INSERT OR IGNORE INTO friend (player_id, friend_id) VALUES (?, ?)",
        (player_id, friend_id),
    )
    db.execute(
        "INSERT OR IGNORE INTO friend (player_id, friend_id) VALUES (?, ?)",
        (friend_id, player_id),
    )


def del_friend_info(
    player_id,
    friend_id,
):
    """删除好友关系"""
    db.execute(
        "DELETE FROM friend WHERE player_id=? AND friend_id=?",
        (
            player_id,
            friend_id,
        ),
    )


def get_achieve(player_id, achieve_id):
    """成就列表"""
    cur = db.execute(
        "SELECT achieve_blob FROM achieve WHERE player_id=? AND achieve_id=?",
        (player_id, achieve_id),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    return None


def set_achieve(player_id, achieve_id, achieve_blob):
    db.execute(
        "INSERT OR REPLACE INTO achieve (player_id, achieve_id, achieve_blob) VALUES (?, ?, ?)",
        (player_id, achieve_id, achieve_blob),
    )


def is_quest_completed(player_id, quest_id):
    """任务是否已完成过(链路2 领取过至少一次)。
    quest_id=0 等异常输入按未完成处理。"""
    if not quest_id:
        return False
    b = get_quest(player_id, quest_id)
    if not b or not isinstance(b, (bytes, bytearray)):
        return False

    q = Quest()
    q.ParseFromString(b)
    return q.complete_count >= 1


def get_quest(player_id=None, quest_id=None):
    if quest_id:
        cur = db.execute(
            "SELECT quest_blob FROM quests WHERE player_id=? AND quest_id=?",
            (player_id, quest_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        return None
    else:
        quests = []
        cur = db.execute(
            "SELECT quest_blob FROM quests WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                quests.append(row[0])
        return quests


def delete_quest(player_id, quest_id):
    """删除指定任务，供日常任务跨日换组使用。"""
    db.execute(
        "DELETE FROM quests WHERE player_id=? AND quest_id=?", (player_id, quest_id)
    )


def set_quest(player_id, quest_id, quest_blob):
    db.execute(
        "INSERT OR REPLACE INTO quests (player_id, quest_id, quest_blob) VALUES (?, ?, ?)",
        (player_id, quest_id, quest_blob),
    )


def get_chapter(player_id, chapter_id=None):
    if chapter_id:
        cur = db.execute(
            "SELECT chapter_blob FROM chapters WHERE player_id=? AND chapter_id=?",
            (player_id, chapter_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        return None
    else:
        chapters = []
        cur = db.execute(
            "SELECT chapter_blob FROM chapters WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                chapters.append(row[0])
        return chapters


def set_chapter(player_id, chapter_id, chapter_blob):
    db.execute(
        "INSERT OR REPLACE INTO chapters (player_id, chapter_id, chapter_blob) VALUES (?, ?, ?)",
        (player_id, chapter_id, chapter_blob),
    )


def get_treasure_box(player_id, box_id=None):
    if box_id or box_id == 0:  # 瓶中小径的宝箱为0
        cur = db.execute(
            "SELECT box_blob FROM treasure_box WHERE player_id=? AND box_id=?",
            (player_id, box_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    else:
        boxs = []
        cur = db.execute(
            "SELECT box_blob FROM treasure_box WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                boxs.append(row[0])
        return boxs


def get_treasure_box_records(player_id):
    cur = db.execute(
        "SELECT box_id, box_blob FROM treasure_box WHERE player_id=?",
        (player_id,),
    )
    return cur.fetchall()


def set_treasure_box(player_id, box_id, box_blob):
    db.execute(
        "INSERT OR REPLACE INTO treasure_box (player_id, box_id, box_blob) VALUES (?, ?, ?)",
        (player_id, box_id, box_blob),
    )


def delete_treasure_box(player_id, box_id):
    db.execute(
        "DELETE FROM treasure_box WHERE player_id=? AND box_id=?",
        (player_id, box_id),
    )


def get_life(player_id, life_index=None):
    cur = db.execute(
        "SELECT life_blob FROM life_info WHERE player_id=?",
        (player_id,),
    )
    row = cur.fetchone()
    if row:
        if life_index:
            return pickle.loads(row[0]).get(life_index)
        else:
            return pickle.loads(row[0])


def set_life(player_id, life_index, life_blob):
    life_list = get_life(player_id)
    life_list[life_index] = life_blob
    db.execute(
        f"INSERT OR REPLACE INTO life_info (player_id, life_blob) VALUES (?, ?)",
        (player_id, pickle.dumps(life_list)),
    )


def get_mail(player_id, mail_id=None):
    if mail_id:
        cur = db.execute(
            "SELECT mail_blob FROM mail WHERE player_id=? AND mail_id=?",
            (player_id, mail_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    else:
        cur = db.execute(
            "SELECT mail_blob FROM mail WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        mails = []
        if rows:
            for row in rows:
                mails.append(row[0])
        return mails


def set_mail(player_id, mail_id, mail_blob):
    db.execute(
        "INSERT OR REPLACE INTO mail (player_id, mail_id, mail_blob) VALUES (?, ?, ?)",
        (player_id, mail_id, mail_blob),
    )


def del_mail(
    player_id,
    mail_id,
):
    db.execute(
        "DELETE FROM mail WHERE player_id=? AND mail_id=?",
        (
            player_id,
            mail_id,
        ),
    )


def get_instance_id(player_id, no_change=False):
    cur = db.execute(
        "SELECT instance_id FROM instance WHERE player_id=?",
        (player_id,),
    )
    row = cur.fetchone()
    if row:
        if no_change:
            return row[0] + 1
        instance_id = row[0] + 1
    else:
        instance_id = 1
    db.execute(
        f"INSERT OR REPLACE INTO instance (player_id, instance_id) VALUES (?, ?)",
        (player_id, instance_id),
    )
    return instance_id


def get_bless_tree(player_id, def_id=0):
    if def_id:
        cur = db.execute(
            "SELECT tree_blob FROM bless_tree WHERE player_id=? AND def_id=?",
            (player_id, def_id),
        )
        row = cur.fetchone()
        return pickle.loads(row[0]) if row else []
    else:
        cur = db.execute(
            "SELECT def_id,tree_blob FROM bless_tree WHERE player_id=? ",
            (player_id,),
        )
        rows = cur.fetchall()
        trees = {}
        if rows:
            for row in rows:
                trees[row[0]] = pickle.loads(row[1])
        return trees


def set_bless_tree(player_id, def_id, tree_ids: list):
    db.execute(
        "INSERT OR REPLACE INTO bless_tree (player_id, def_id, tree_blob) VALUES (?, ?, ?)",
        (player_id, def_id, pickle.dumps(tree_ids)),
    )


def get_ability_tree(player_id, scene_id=0):
    if scene_id:
        cur = db.execute(
            "SELECT tree_blob FROM ability_tree WHERE player_id=? AND scene_id=?",
            (player_id, scene_id),
        )
        row = cur.fetchone()
        return pickle.loads(row[0]) if row else []
    else:
        cur = db.execute(
            "SELECT scene_id,tree_blob FROM ability_tree WHERE player_id=? ",
            (player_id,),
        )
        rows = cur.fetchall()
        trees = {}
        if rows:
            for row in rows:
                trees[row[0]] = pickle.loads(row[1])
        return trees


def set_ability_tree(player_id, scene_id, tree_ids: list):
    db.execute(
        "INSERT OR REPLACE INTO ability_tree (player_id, scene_id, tree_blob) VALUES (?, ?, ?)",
        (player_id, scene_id, pickle.dumps(tree_ids)),
    )


def set_collection(player_id, item_id, collection_type, item_blob):
    db.execute(
        "INSERT OR REPLACE INTO collections (player_id, item_id, collection_type, item_blob) VALUES (?, ?, ?, ?)",
        (player_id, item_id, collection_type, item_blob),
    )


def get_collection(player_id, item_id=None):
    if item_id:
        cur = db.execute(
            "SELECT collection_type,item_blob FROM collections WHERE player_id=? AND item_id=?",
            (player_id, item_id),
        )
        row = cur.fetchone()
        if row:
            return row
    else:
        cur = db.execute(
            "SELECT collection_type,item_blob FROM collections WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        collections = []
        if rows:
            for row in rows:
                collections.append(row)
        return collections


def add_gacha_record(player_id, gacha_id, item_id):
    db.execute(
        """
        INSERT INTO gacha_record (player_id, gacha_id, item_id, gacha_time)
        VALUES (?, ?, ?, ?)
        """,
        (player_id, gacha_id, item_id, int(time.time())),
    )


def get_gacha_records(player_id, gacha_id, page=1, page_size=5):
    offset = (page - 1) * page_size
    cur = db.execute(
        """
        SELECT item_id, gacha_time
        FROM gacha_record
        WHERE player_id=? AND gacha_id=?
        ORDER BY gacha_time DESC
        LIMIT ? OFFSET ?
        """,
        (player_id, gacha_id, page_size, offset),
    )
    return cur.fetchall()


def get_total_gacha_num(player_id, gacha_id):
    cur = db.execute(
        "SELECT COUNT(*) FROM gacha_record WHERE player_id=? AND gacha_id=?",
        (player_id, gacha_id),
    )
    return cur.fetchone()[0]


def set_gacha_guarantee(player_id, gacha_id, guarantee):
    db.execute(
        "INSERT OR REPLACE INTO gacha_guarantee (player_id, gacha_id, guarantee) VALUES (?, ?, ?)",
        (player_id, gacha_id, guarantee),
    )


def get_gacha_guarantee(player_id, gacha_id):
    cur = db.execute(
        "SELECT guarantee FROM gacha_guarantee WHERE player_id=? AND gacha_id=?",
        (player_id, gacha_id),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    else:
        return 0


def set_furniture(scene_id, channel_id, player_id, furniture_id, furniture_detail_blob):
    db.execute(
        "INSERT OR REPLACE INTO furnitures (scene_id, channel_id, player_id, furniture_id, furniture_detail_blob) VALUES (?, ?, ?, ?, ?)",
        (scene_id, channel_id, player_id, furniture_id, furniture_detail_blob),
    )


def get_furniture(scene_id, channel_id, player_id=None, furniture_id=None):
    if not player_id and not furniture_id:
        cur = db.execute(
            "SELECT * FROM furnitures WHERE scene_id=? AND channel_id=?",
            (scene_id, channel_id),
        )
        rows = cur.fetchall()
        furnitures = []
        if rows:
            for row in rows:
                furnitures.append(row)
        return furnitures

    else:
        cur = db.execute(
            "SELECT * FROM furnitures WHERE scene_id=? AND channel_id=? AND player_id=? AND furniture_id=?",
            (scene_id, channel_id, player_id, furniture_id),
        )
        row = cur.fetchone()
        if row:
            return row


def del_furniture(scene_id, channel_id, player_id, furniture_id):
    db.execute(
        "DELETE FROM furnitures WHERE scene_id=? AND channel_id=? AND player_id=? AND furniture_id=?",
        (scene_id, channel_id, player_id, furniture_id),
    )


def get_area(player_id, scene_id, area_id=None) -> list:
    if area_id:
        cur = db.execute(
            "SELECT area_blob FROM areas WHERE player_id=? AND scene_id=? AND area_id=?",
            (player_id, scene_id, area_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    else:
        areas = []
        cur = db.execute(
            "SELECT area_blob FROM areas WHERE player_id=? AND scene_id=?",
            (player_id, scene_id),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                areas.append(row[0])
        return areas


def set_area(player_id, scene_id, area_id, area_blob):
    db.execute(
        "INSERT OR REPLACE INTO areas (player_id, scene_id, area_id, area_blob) VALUES (?, ?, ?, ?)",
        (player_id, scene_id, area_id, area_blob),
    )


def get_challenge(player_id, scene_id, challenge_id=None) -> list:
    if challenge_id:
        cur = db.execute(
            "SELECT challenge_blob FROM challenges WHERE player_id=? AND scene_id=? AND challenge_id=?",
            (player_id, scene_id, challenge_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    else:
        challenges = []
        cur = db.execute(
            "SELECT challenge_blob FROM challenges WHERE player_id=? AND scene_id=?",
            (player_id, scene_id),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                challenges.append(row[0])
        return challenges


def set_challenge(player_id, scene_id, challenge_id, challenge_blob):
    db.execute(
        "INSERT OR REPLACE INTO challenges (player_id, scene_id, challenge_id, challenge_blob) VALUES (?, ?, ?, ?)",
        (player_id, scene_id, challenge_id, challenge_blob),
    )


def get_dungeon(player_id, dungeon_id=None) -> list:
    """team在一个字段存储两位角色, 对应上下间"""
    if dungeon_id:
        cur = db.execute(
            "SELECT dungeon_blob FROM dungeons WHERE player_id=? AND dungeon_id=?",
            (player_id, dungeon_id),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    else:
        dungeons = {}
        cur = db.execute(
            "SELECT dungeon_id, dungeon_blob FROM dungeons WHERE player_id=?",
            (player_id,),
        )
        rows = cur.fetchall()
        if rows:
            for row in rows:
                dungeons[row[0]] = row[1]
        return dungeons


def set_dungeon(player_id, dungeon_id, dungeon_blob):
    db.execute(
        "INSERT OR REPLACE INTO dungeons (player_id, dungeon_id, dungeon_blob) VALUES (?, ?, ?)",
        (player_id, dungeon_id, dungeon_blob),
    )


def get_boss_rush_info(player_id, season_id):
    cur = db.execute(
        "SELECT info_blob FROM boss_rush_info WHERE player_id=? AND season_id=?",
        (player_id, season_id),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    return None


def set_boss_rush_info(player_id, season_id, info_blob):
    db.execute(
        "INSERT OR REPLACE INTO boss_rush_info (player_id, season_id, info_blob) VALUES (?, ?, ?)",
        (player_id, season_id, info_blob),
    )


def add_character(player_id, character_id, c=None):
    for i in res["Character"]["character"]["datas"]:
        if i["i_d"] == character_id:
            if c == None:
                c = Character()

            c.character_id = i["i_d"]
            c.level = 1
            c.max_level = 20
            c.exp = 0
            c.star = 0
            c.gather_weapon = 0

            t1 = c.equipment_presets.add()
            t1.preset_index = 0
            t1.weapon = 0

            t1.armors.add()
            t1.armors.add().equip_type = EEquipType.EEquipType_Chest
            t1.armors.add().equip_type = EEquipType.EEquipType_Hand
            t1.armors.add().equip_type = EEquipType.EEquipType_Shoes
            t1.posters.add()
            t1.posters.add().poster_index = 1
            t1.posters.add().poster_index = 2

            c.equipment_presets.add().preset_index = 1
            c.equipment_presets.add().preset_index = 2

            for iter in range(0, 3):
                o = c.outfit_presets.add()
                item = ItemDetail()
                item.main_item.item_tag = EBagItemTag.EBagItemTag_Fashion
                item.main_item.outfit.dye_schemes.add().is_un_lock = True
                o.hat = i.get("hat_i_d") or 0
                if o.hat:
                    item.main_item.item_id = o.hat
                    item.main_item.outfit.outfit_id = o.hat
                    set_item_detail(player_id, item.SerializeToString(), o.hat)
                o.hair = i.get("hair_i_d") or 0
                if o.hair:
                    item.main_item.item_id = o.hair
                    item.main_item.outfit.outfit_id = o.hair
                    set_item_detail(player_id, item.SerializeToString(), o.hair)
                o.clothes = i.get("cloth_i_d") or 0
                if o.clothes:
                    item.main_item.item_id = o.clothes
                    item.main_item.outfit.outfit_id = o.clothes
                    set_item_detail(player_id, item.SerializeToString(), o.clothes)
                o.ornament = (i.get("orn_i_d") and i.get("orn_i_d")[0]) or 0
                if o.ornament:
                    item.main_item.item_id = o.ornament
                    item.main_item.outfit.outfit_id = o.ornament
                    set_item_detail(player_id, item.SerializeToString(), o.ornament)
                o.preset_index = iter
                o.outfit_hide_info.CopyFrom(OutfitHideInfo())

            c.character_appearance.badge = 5000
            c.character_appearance.umbrella_id = 4050
            c.character_appearance.insect_net_instance_id = 1004001
            c.character_appearance.logging_axe_instance_id = 1002001
            c.character_appearance.water_bottle_instance_id = 1005001
            c.character_appearance.mining_hammer_instance_id = 1003001
            c.character_appearance.collection_gloves_instance_id = 1001001
            c.character_appearance.fishing_rod_instance_id = 1006001

            spells = i.get("spell_i_ds", [])
            ex_spells = i.get("ex_spell_i_ds", [])

            s = c.character_skill_list.add()
            s.skill_id = spells[0] if len(spells) > 0 else 0
            s.skill_level = 1

            s = c.character_skill_list.add()
            s.skill_id = spells[1] if len(spells) > 1 else 0
            s.skill_level = 1

            s = c.character_skill_list.add()
            s.skill_id = ex_spells[0] if len(ex_spells) > 0 else 0
            s.skill_level = 1

            default_weapon_id = i.get("default_weapon_i_d") or 1101104
            item = make_item(default_weapon_id, 1, player_id, equipment_level=1)
            item.main_item.weapon.wearer_id = i["i_d"]
            instance_id = item.main_item.weapon.instance_id
            set_item_detail(
                player_id,
                item.SerializeToString(),
                None,
                instance_id,
            )
            c.equipment_presets[0].weapon = instance_id
            db.execute(
                "INSERT OR IGNORE INTO characters (player_id, character_id, character_blob) VALUES (?, ?, ?)",
                (player_id, i["i_d"], c.SerializeToString()),
            )
            return c


# ============ 通用玩家 KV(player_kv 表) ============
# 用于无独立表的小状态: 档案/手机壳/能力等级/购买次数/签到/战令/


def get_kv(player_id, ns, k, default=None):
    cur = db.execute(
        "SELECT v FROM player_kv WHERE player_id=? AND ns=? AND k=?",
        (player_id, ns, str(k)),
    )
    row = cur.fetchone()
    return row[0] if row else default


def get_kv_keys(player_id, ns):
    """列出某命名空间下的全部 key"""
    cur = db.execute(
        "SELECT k FROM player_kv WHERE player_id=? AND ns=?", (player_id, ns)
    )
    return [row[0] for row in cur.fetchall()]


def get_quest_trackers(player_id):
    return _quest_trackers(player_id)


def _story_chapter_map():
    """story_id -> (chapter_cfg, index) 映射"""
    m = {}
    for chapter in res["Story"]["story_chapter"]["datas"]:
        for sid in chapter.get("story_list", ()):
            m[sid] = chapter
    return m


def is_story_rewarded(player_id, story_id):
    """剧情奖励是否已领取(存在于任一章节的 rewarded_story_ids);
    章节外剧情(1000401~1000414/1000509/1000510 等)存于 0 号桶
    (get_chapter 对 chapter_id=0 走全量列表分支, 需单独扫描)"""
    chapter = _story_chapter_map().get(story_id)
    cid = chapter["i_d"] if chapter else 0
    if cid == 0:
        for b in get_chapter(player_id) or ():
            c = Chapter()
            c.ParseFromString(b)
            if c.chapter_id == 0:
                return story_id in c.rewarded_story_ids
        return False
    blob = get_chapter(player_id, cid)
    if not blob or not isinstance(blob, (bytes, bytearray)):
        return False
    c = Chapter()
    c.ParseFromString(blob)
    return story_id in c.rewarded_story_ids


def add_player_exp(player_id, amount):
    """累加玩家经验并按 Level.player_level.need_exp 升级, 返回 (level, exp)。
    need_exp 为当前等级升到下一级所需经验。"""
    row = db.execute(
        "SELECT level, exp FROM players WHERE player_id=?", (player_id,)
    ).fetchone()
    level, exp = (row[0], row[1]) if row else (1, 0)
    exp += max(0, amount)
    lv_cfg = {
        e["i_d"]: e.get("need_exp", 0) for e in res["Level"]["player_level"]["datas"]
    }
    while level < len(lv_cfg) and exp >= lv_cfg.get(level, float("inf")):
        exp -= lv_cfg[level]
        level += 1
    db.execute(
        "UPDATE players SET level=?, exp=? WHERE player_id=?", (level, exp, player_id)
    )
    return level, exp


def set_kv(player_id, ns, k, v):
    db.execute(
        "INSERT OR REPLACE INTO player_kv (player_id, ns, k, v) VALUES (?, ?, ?, ?)",
        (player_id, ns, str(k), v),
    )


def del_kv(player_id, ns, k=None):
    if k is None:
        db.execute("DELETE FROM player_kv WHERE player_id=? AND ns=?", (player_id, ns))
    else:
        db.execute(
            "DELETE FROM player_kv WHERE player_id=? AND ns=? AND k=?",
            (player_id, ns, str(k)),
        )


def get_kv_ns(player_id, ns):
    """返回整个命名空间 {k: v}"""
    cur = db.execute(
        "SELECT k, v FROM player_kv WHERE player_id=? AND ns=?", (player_id, ns)
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def incr_kv(player_id, ns, k, delta=1):
    """整数值原子自增, 返回自增后的值(不存在按 0 起)"""
    with lock_db:
        cur = conn.execute(
            "SELECT v FROM player_kv WHERE player_id=? AND ns=? AND k=?",
            (player_id, ns, str(k)),
        )
        row = cur.fetchone()
        val = (int(row[0]) if row and row[0] is not None else 0) + delta
        conn.execute(
            "INSERT OR REPLACE INTO player_kv (player_id, ns, k, v) VALUES (?, ?, ?, ?)",
            (player_id, ns, str(k), val),
        )
        return val


# ============ 统一领奖去重(claimed_rewards 表) ============


def try_claim(player_id, system, key):
    """原子领取: 未领过则记录并返回 True, 已领过返回 False"""
    with lock_db:
        cur = conn.execute(
            "INSERT OR IGNORE INTO claimed_rewards (player_id, system, key, claim_time)"
            " VALUES (?, ?, ?, ?)",
            (player_id, system, str(key), int(time.time())),
        )
        return cur.rowcount > 0


def rollback_claim(player_id, system, key):
    """撤销 try_claim 记录(校验失败时退还领取资格)"""
    with lock_db:
        cur = conn.execute(
            "DELETE FROM claimed_rewards WHERE player_id=? AND system=? AND key=?",
            (player_id, system, str(key)),
        )
        return cur.rowcount > 0


def has_claimed(player_id, system, key):
    cur = db.execute(
        "SELECT 1 FROM claimed_rewards WHERE player_id=? AND system=? AND key=?",
        (player_id, system, str(key)),
    )
    return cur.fetchone() is not None


def get_claimed(player_id, system):
    """返回该系统下已领取的 key 列表(str)"""
    cur = db.execute(
        "SELECT key FROM claimed_rewards WHERE player_id=? AND system=?",
        (player_id, system),
    )
    return [row[0] for row in cur.fetchall()]


def del_claimed(player_id, system, key=None):
    """清除领取记录(每日重置类活动用)"""
    if key is None:
        db.execute(
            "DELETE FROM claimed_rewards WHERE player_id=? AND system=?",
            (player_id, system),
        )
    else:
        db.execute(
            "DELETE FROM claimed_rewards WHERE player_id=? AND system=? AND key=?",
            (player_id, system, str(key)),
        )


# ============ 照片分享(photo_shares 表) ============


def add_photo_share(share_code, player_id, title, data_blob):
    db.execute(
        "INSERT OR REPLACE INTO photo_shares"
        " (share_code, player_id, title, data_blob, likes, create_time)"
        " VALUES (?, ?, ?, ?, COALESCE((SELECT likes FROM photo_shares WHERE share_code=?), 0), ?)",
        (share_code, player_id, title, data_blob, share_code, int(time.time())),
    )


def get_photo_share(share_code=None, player_id=None, limit=50):
    """share_code 查单条(返回 row 或 None); player_id 查玩家的; 都不传返回最新 limit 条。
    row: (share_code, player_id, title, data_blob, likes, create_time)"""
    if share_code is not None:
        cur = db.execute(
            "SELECT share_code, player_id, title, data_blob, likes, create_time"
            " FROM photo_shares WHERE share_code=?",
            (share_code,),
        )
        return cur.fetchone()
    if player_id is not None:
        cur = db.execute(
            "SELECT share_code, player_id, title, data_blob, likes, create_time"
            " FROM photo_shares WHERE player_id=? ORDER BY create_time DESC LIMIT ?",
            (player_id, limit),
        )
        return cur.fetchall()
    cur = db.execute(
        "SELECT share_code, player_id, title, data_blob, likes, create_time"
        " FROM photo_shares ORDER BY create_time DESC LIMIT ?",
        (limit,),
    )
    return cur.fetchall()


def set_photo_share_info(share_code, title=None, likes_delta=0, data_blob=None):
    with lock_db:
        if title is not None:
            conn.execute(
                "UPDATE photo_shares SET title=? WHERE share_code=?",
                (title, share_code),
            )
        if likes_delta:
            conn.execute(
                "UPDATE photo_shares SET likes=MAX(0, likes+?) WHERE share_code=?",
                (likes_delta, share_code),
            )
        if data_blob is not None:
            conn.execute(
                "UPDATE photo_shares SET data_blob=? WHERE share_code=?",
                (data_blob, share_code),
            )


def del_photo_share(share_code, player_id=None):
    """player_id 传入时校验归属, 返回是否删除"""
    with lock_db:
        if player_id is not None:
            cur = conn.execute(
                "DELETE FROM photo_shares WHERE share_code=? AND player_id=?",
                (share_code, player_id),
            )
        else:
            cur = conn.execute(
                "DELETE FROM photo_shares WHERE share_code=?", (share_code,)
            )
        return cur.rowcount > 0


# ============ 兑换码(redeem_codes / redeem_code_uses 表) ============
# rewards 格式: "item_id:num,item_id:num,..."; 由 GM 命令/工具写入码库


def add_redeem_code(code, rewards, max_uses=0, expire_time=0, code_type="redeem"):
    db.execute(
        "INSERT OR REPLACE INTO redeem_codes (code, code_type, rewards, max_uses, used, expire_time)"
        " VALUES (?, ?, ?, ?, COALESCE((SELECT used FROM redeem_codes WHERE code=?), 0), ?)",
        (code, code_type, rewards, max_uses, code, expire_time),
    )


def use_redeem_code(player_id, code, code_type=None):
    """原子核销兑换码。

    返回 (status, rewards_str):
    status: 0=成功, 1=码不存在/类型不符, 2=已过期, 3=次数用尽, 4=该玩家已用过
    """
    with lock_db:
        cur = conn.execute(
            "SELECT code_type, rewards, max_uses, used, expire_time FROM redeem_codes WHERE code=?",
            (code,),
        )
        row = cur.fetchone()
        if not row or (code_type is not None and row[0] != code_type):
            return 1, ""
        ctype, rewards, max_uses, used, expire = row
        if expire and time.time() > expire:
            return 2, ""
        if max_uses and used >= max_uses:
            return 3, ""
        cur = conn.execute(
            "INSERT OR IGNORE INTO redeem_code_uses (code, player_id, use_time) VALUES (?, ?, ?)",
            (code, player_id, int(time.time())),
        )
        if cur.rowcount == 0:
            return 4, ""
        conn.execute("UPDATE redeem_codes SET used=used+1 WHERE code=?", (code,))
        return 0, rewards or ""


# ============ 活动通用: 发奖/扣道具/战令经验/转盘记录 ============


def grant_rewards(player_id, reward_list, rsp_rewards, pack_notice):
    """发放物品并写入回包与 PackNotice。

    reward_list: [(item_id, num), ...]
    rsp_rewards: Rsp 中的 repeated ItemDetail 字段(数量填本次新增量), 可为 None
    pack_notice: PackNotice(items 填发放后的总量)

    委托 utils/items.py 的 per-player lock, 不再使用 lock_db 全局锁。
    """

    items_util.grant_items(
        player_id, reward_list, rsp_items=rsp_rewards, pack_notice=pack_notice
    )


def consume_item(player_id, item_id, num, pack):
    """扣道具, 成功把扣后余量写入 pack 并返回 True。

    委托 utils/items.py 的 per-player lock, 不再使用 lock_db 全局锁。
    """

    return items_util.consume_items(player_id, [(item_id, num)], pack_notice=pack)


def _bp_level_exps(battle_pass_id):
    """该战令各级所需经验列表; 表缺失返回 None(用 1000/级兜底)"""
    _tab = res.get("BattlePass")
    _tab = _tab.get("battle_pass") if isinstance(_tab, dict) else None
    _tab = _tab.get("datas") if isinstance(_tab, dict) else None
    for bp in _tab if isinstance(_tab, (list, tuple)) else ():
        if bp["i_d"] == activity_state.template_id(battle_pass_id):
            exps = [
                lv.get("exp", Config.BP_EXP_PER_LEVEL)
                for lv in bp.get("battle_pass_level_ups", ())
            ]
            return exps or None
    return None


def _bp_lv_from_total(battle_pass_id, total):
    exps = _bp_level_exps(battle_pass_id)
    if not exps:
        return total // Config.BP_EXP_PER_LEVEL, total % Config.BP_EXP_PER_LEVEL
    lv, rest = 0, total
    for need in exps:
        need = need or Config.BP_EXP_PER_LEVEL
        if rest < need:
            break
        rest -= need
        lv += 1
    return lv, rest


def bp_add_exp(player_id, battle_pass_id, exp):
    """增加战令经验(持久化到 player_kv ns=battle_pass), 返回 (lv, total_exp, current_exp)"""
    total = incr_kv(player_id, "battle_pass", battle_pass_id, exp)
    lv, cur = _bp_lv_from_total(battle_pass_id, total)
    return lv, total, cur


def bp_get_exp(player_id, battle_pass_id):
    """读取战令经验, 返回 (lv, total_exp, current_exp)"""
    total = int(get_kv(player_id, "battle_pass", battle_pass_id, 0) or 0)
    lv, cur = _bp_lv_from_total(battle_pass_id, total)
    return lv, total, cur


def add_turntable_record(player_id, activity_id, index, item_id, item_num, draw_time):
    """写入一条转盘抽奖记录"""
    db.execute(
        "INSERT INTO turntable_record"
        ' (player_id, activity_id, "index", item_id, item_num, draw_time)'
        " VALUES (?, ?, ?, ?, ?, ?)",
        (player_id, activity_id, index, item_id, item_num, draw_time),
    )


def get_turntable_records(player_id, activity_id, page=1, page_size=10):
    """分页查询转盘抽奖记录(最新在前), 返回 (records, total, total_page)。
    records: [(index, item_id, item_num, draw_time), ...]"""
    cur = db.execute(
        "SELECT COUNT(*) FROM turntable_record WHERE player_id=? AND activity_id=?",
        (player_id, activity_id),
    )
    total = cur.fetchone()[0]
    total_page = (total + page_size - 1) // page_size if page_size else 1
    offset = (page - 1) * page_size
    cur = db.execute(
        'SELECT "index", item_id, item_num, draw_time'
        " FROM turntable_record WHERE player_id=? AND activity_id=?"
        " ORDER BY draw_time DESC, id DESC LIMIT ? OFFSET ?",
        (player_id, activity_id, page_size, offset),
    )
    records = cur.fetchall()
    return records, total, total_page


def get_turntable_used_counts(player_id, activity_id):
    """返回该活动各格已抽次数 {index: count}, 用于 limit_num 校验"""
    cur = db.execute(
        'SELECT "index", COUNT(*) FROM turntable_record'
        ' WHERE player_id=? AND activity_id=? GROUP BY "index"',
        (player_id, activity_id),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def has_turntable_drawn(player_id, activity_id):
    """是否在该活动抽过奖(用于首抽判定)"""
    cur = db.execute(
        "SELECT 1 FROM turntable_record WHERE player_id=? AND activity_id=? LIMIT 1",
        (player_id, activity_id),
    )
    return cur.fetchone() is not None


# ============ 花园/探索/间隙/方案/点赞持久化(player_kv) ============
# 原 utils/garden_state.py 的 6 个内存 dict 迁移至此,


def get_garden_password(player_id):
    """返回 (password, expire_time_ms)"""
    pw = get_kv(player_id, "garden", "password")
    if pw is None:
        return "", 0
    return pickle.loads(pw)


def set_garden_password(player_id, password, expire_time):
    set_kv(player_id, "garden", "password", pickle.dumps((password, expire_time)))


def consume_like(player_id, limit=10):
    """消耗一次今日点赞次数, 返回剩余次数; 用尽返回 None。
    limit 为每日上限(默认 10, 与 Config.DAILY_LIKE_LIMIT 一致)。"""

    day = datetime.date.today().isoformat()
    with lock_db:
        cur = conn.execute(
            "SELECT v FROM player_kv WHERE player_id=? AND ns='garden' AND k='like_state'",
            (player_id,),
        )
        row = cur.fetchone()
        if row:
            st = pickle.loads(row[0])
        else:
            st = {"day": day, "left": limit}
        if st["day"] != day:
            st = {"day": day, "left": limit}
        if st["left"] <= 0:
            return None
        st["left"] -= 1
        conn.execute(
            "INSERT OR REPLACE INTO player_kv (player_id, ns, k, v) VALUES (?, 'garden', 'like_state', ?)",
            (player_id, pickle.dumps(st)),
        )
        return st["left"]


def get_like_left(player_id, limit=10):
    """返回今日剩余点赞次数"""

    day = datetime.date.today().isoformat()
    raw = get_kv(player_id, "garden", "like_state")
    if raw is None:
        return limit
    st = pickle.loads(raw)
    if st["day"] != day:
        return limit
    return st["left"]


def add_like_record(target_player_id, liker_player_id):
    """记录一次点赞(被赞者维度)"""
    with lock_db:
        cur = conn.execute(
            "SELECT v FROM player_kv WHERE player_id=? AND ns='garden' AND k='like_records'",
            (target_player_id,),
        )
        row = cur.fetchone()
        records = pickle.loads(row[0]) if row else {}
        records[liker_player_id] = records.get(liker_player_id, 0) + 1
        conn.execute(
            "INSERT OR REPLACE INTO player_kv (player_id, ns, k, v) VALUES (?, 'garden', 'like_records', ?)",
            (target_player_id, pickle.dumps(records)),
        )


def get_like_records(player_id):
    """返回 [(点赞者 player_id, 次数)]"""
    raw = get_kv(player_id, "garden", "like_records")
    if raw is None:
        return []
    return list(pickle.loads(raw).items())


# --- 探索派遣 ---


def get_explore(player_id, explore_id):
    """获取玩家某探索点的进度 dict; 不存在返回默认值"""
    raw = get_kv(player_id, "explore", str(explore_id))
    if raw is None:
        return {
            "times": 0,
            "start_time": 0,
            "is_quick_finish": False,
            "collect_reward": False,
        }
    return pickle.loads(raw)


def set_explore(player_id, explore_id, state):
    set_kv(player_id, "explore", str(explore_id), pickle.dumps(state))


def get_all_explores(player_id):
    """返回 {explore_id_str: state_dict}"""
    return get_kv_ns(player_id, "explore")


# --- 好友间隙 ---


def get_interval(player_id):
    """获取玩家间隙状态 dict; 不存在返回 None"""
    raw = get_kv(player_id, "interval", "state")
    if raw is None:
        return None
    return pickle.loads(raw)


def set_interval(player_id, state):
    set_kv(player_id, "interval", "state", pickle.dumps(state))


def del_interval(player_id):
    del_kv(player_id, "interval", "state")


# --- 家具方案 ---


def get_schemes(player_id):
    """返回 {scheme_id: {"name": str, "furnitures": [...]}}"""
    raw = get_kv(player_id, "garden", "schemes")
    if raw is None:
        return {}
    return pickle.loads(raw)


def set_schemes(player_id, schemes):
    set_kv(player_id, "garden", "schemes", pickle.dumps(schemes))


# --- 餐厅经营 ---


def get_restaurant_state(player_id, activity_id):
    """获取餐厅经营状态 dict; 不存在返回 None"""
    raw = get_kv(player_id, "restaurant", str(activity_id))
    if raw is None:
        return None
    return pickle.loads(raw)


def set_restaurant_state(player_id, activity_id, state):
    set_kv(player_id, "restaurant", str(activity_id), pickle.dumps(state))


# --- 生活技能 ---


def get_life_skills(player_id, life_type):
    """获取生活技能 {skill_id: (lv, start_study_time)}; 不存在返回 {}"""
    raw = get_kv(player_id, "life_skill", str(life_type))
    if raw is None:
        return {}
    return pickle.loads(raw)


def set_life_skills(player_id, life_type, skills):
    set_kv(player_id, "life_skill", str(life_type), pickle.dumps(skills))


# --- 遭遇战状态 ---


def get_encounter_states(player_id):
    """获取玩家所有遭遇战状态 {encounter_id: (state, box_id)}; 不存在返回 {}"""
    raw = get_kv(player_id, "encounter", "states")
    if raw is None:
        return {}
    return pickle.loads(raw)


def set_encounter_state(player_id, encounter_id, state, box_id=0):
    """记录/更新单个遭遇战状态; get→改→set 在 lock_db 内完成"""
    with lock_db:
        raw = conn.execute(
            "SELECT v FROM player_kv WHERE player_id=? AND ns='encounter' AND k='states'",
            (player_id,),
        ).fetchone()
        states = pickle.loads(raw[0]) if raw else {}
        states[encounter_id] = (state, box_id)
        conn.execute(
            "INSERT OR REPLACE INTO player_kv (player_id, ns, k, v) VALUES (?, 'encounter', 'states', ?)",
            (player_id, pickle.dumps(states)),
        )


def get_player_ids():
    """全部已知玩家 id(榜单等跨玩家聚合用)"""
    cur = db.execute("SELECT player_id FROM players;")
    return [r[0] for r in cur.fetchall()]
