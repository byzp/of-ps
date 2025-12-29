import sqlite3
import time
import os
import logging
import pickle
import threading
import secrets
from contextlib import contextmanager

from config import Config
from utils.res_loader import res
import proto.OverField_pb2 as Character_pb2
import proto.OverField_pb2 as pb

logger = logging.getLogger(__name__)

db = None
lock_db = threading.Lock()


class db_warp:
    __slots__ = ("_conn", "_rw_lock")

    def __init__(self, conn):
        self._conn = conn
        self._rw_lock = lock_db

    def execute(self, *args, **kwargs):
        with self._rw_lock:
            return self._conn.execute(*args, **kwargs)


def exit():
    global db
    with lock_db:
        conn.commit()
        if Config.IN_MEMORY:
            disk = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
            conn.backup(disk)
            disk.commit()
            disk.close()
        conn.close()


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

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            user_token TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS players (
            player_id INTEGER PRIMARY KEY,
            player_name TEXT,
            level INTEGER DEFAULT 1,
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
            pendant INTEGER DEFAULT 0
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
            furniture_limit_num INTEGER DEFAULT 500000,
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

        CREATE TABLE IF NOT EXISTS collections (
            player_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            collection_type INTEGER NOT NULL,
            item_blob BLOB NOT NULL,
            PRIMARY KEY (player_id, item_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id) ON DELETE CASCADE
        );

        INSERT OR IGNORE INTO users (id, username, password, user_token) VALUES (1000000, "", "", "");

    """
    )


def init_player(player_id):
    """初始化新用户数据"""
    cur_time = int(time.time())
    player_name = ""
    player_unlock_data = (
        res.get("PlayerUnlock", {}).get("player_unlock", {}).get("datas", [])
    )
    unlock_func_ids = [item["i_d"] for item in player_unlock_data]
    unlock_funcs = pickle.dumps(unlock_func_ids)

    team = pickle.dumps((101001, 101002, 101003))

    db.execute(
        """INSERT OR IGNORE INTO players 
        (player_id, player_name, register_time, create_time, unlock_functions, team) 
        VALUES (?, ?, ?, ?, ?, ?)""",
        (player_id, player_name, cur_time, cur_time, unlock_funcs, team),
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
    datas = res.get("Character", {}).get("character", {}).get("datas", [])
    for i in datas:
        c = Character_pb2.Character()

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
        t1.armors.add().equip_type = pb.EEquipType_Chest
        t1.armors.add().equip_type = pb.EEquipType_Hand
        t1.armors.add().equip_type = pb.EEquipType_Shoes
        t1.posters.add()
        t1.posters.add().poster_index = 1
        t1.posters.add().poster_index = 2

        c.equipment_presets.add().preset_index = 1
        c.equipment_presets.add().preset_index = 2

        for iter in range(0, 3):
            o = c.outfit_presets.add()
            item = pb.ItemDetail()
            item.main_item.item_tag = pb.EBagItemTag_Fashion
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
            o.outfit_hide_info.CopyFrom(pb.OutfitHideInfo())

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

        db.execute(
            "INSERT INTO characters (player_id, character_id, character_blob) VALUES (?, ?, ?)",
            (player_id, i["i_d"], c.SerializeToString()),
        )

    # 初始化物品(星石+10, 用于第一次改名)
    item = pb.ItemDetail()
    tmp = item.main_item
    tmp.item_id = 102
    tmp.item_tag = pb.EBagItemTag_Currency
    tmp.base_item.item_id = 102
    tmp.base_item.num = 10

    db.execute(
        "INSERT OR REPLACE INTO items (player_id, item_id, item_detail_blob) VALUES (?, ?, ?)",
        (player_id, 102, item.SerializeToString()),
    )

    # 初始化 Achieve
    for achieve in res["Achieve"]["achieve"]["datas"]:
        if achieve.get("i_d", 0):
            tmp = pb.Achieve()
            tmp.achieve_id = achieve["i_d"]
            set_achieve(player_id, achieve["i_d"], tmp.SerializeToString())

    # 初始化任务
    for quest in res["Quest"]["quest"]["datas"]:
        tmp = pb.Quest()
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
                            for achieve in res["Achieve"]["achieve"]["datas"]:
                                if achieve["i_d"] == achieve_condition_id:
                                    tmp1.progress = achieve.get("count_param", 0)
                                    break
                            tmp1.status = pb.QuestStatus_Finish
                    break
        tmp.status = pb.QuestStatus_Finish
        tmp.bonus_times = 1
        set_quest(player_id, quest["i_d"], tmp.SerializeToString())
    # 初始化任务章节
    for chapter in res["Story"]["story_chapter"]["datas"]:
        tmp = pb.Chapter()
        tmp.chapter_id = chapter["i_d"]
        for story in chapter["story_list"]:
            tmp.rewarded_story_ids.append(story)
        set_chapter(player_id, chapter["i_d"], tmp.SerializeToString())
    # 初始化生活信息
    life_list = {}
    for i in range(1, 7):
        tmp = pb.LifeBaseInfo()
        tmp.life_type = i
        tmp.level = 0
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
    # for collection_t in res["CollectionItem"]["collection_item"]["datas"]:
    #     collection=pb.PBCollectionRewardData()
    #     collection.item_id=collection_t["i_d"]
    #     set_collection(player_id,collection_t["i_d"],collection_t["new_collection_type"],collection.SerializeToString())

    # 一封欢迎邮件
    mail = pb.MailBriefData()
    mail.mail_id = 1
    mail.sender = "aac"
    mail.content_type = pb.MailContentType_TEXT
    mail.send_time = int(time.time())
    mail.title = "of-ps"
    mail.content = "此项目以AGPL开源, 仓库地址<color=#66ccff><b>https://github.com/byzp/of-ps</b></color>, 觉得有用点个star吧\n\n"
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
    # 如果是BLOB类型字段，需要反序列化
    is_blob_field = info_name in ["team", "unlock_functions"]

    if isinstance(player_index, int):
        cur = db.execute(
            f"SELECT {info_name} FROM players WHERE player_id=?", (player_index,)
        )
        row = cur.fetchone()
        if row:
            if is_blob_field and row[0]:
                return pickle.loads(row[0])
            return row[0]
        return None
    else:
        cur = db.execute(
            f"SELECT {info_name} FROM players WHERE player_name=?", (player_index,)
        )
        row = cur.fetchone()
        if row:
            if is_blob_field and row[0]:
                return pickle.loads(row[0])
            return row[0]
        return None


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


def set_garden_info(player_id, field1, field2, field3, field4, field5):
    db.execute(
        """INSERT OR REPLACE INTO garden_info 
        (player_id, field1, field2, field3, field4, field5) VALUES (?, ?, ?, ?, ?, ?)""",
        (player_id, field1, field2, field3, field4, int(field5)),
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
    # TODO
    return [
        {"type": 0, "msg": []},
        {"type": 1, "msg": []},
        {"type": 2, "msg": []},
        {"type": 3, "msg": []},
    ]


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
    from utils.res_loader import res

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
            return row[0]
        return None
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


def get_quest(player_id, quest_id=None):
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


def set_quest(player_id, quest_id, quest_blob):
    db.execute(
        "INSERT OR REPLACE INTO quests (player_id, quest_id, quest_blob) VALUES (?, ?, ?)",
        (player_id, quest_id, quest_blob),
    )


def get_chapter(player_id, chapter_id=None):
    if chapter_id:
        cur = db.execute(
            "SELECT quest_blob FROM chapter WHERE player_id=? AND chapter_id=?",
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


def set_treasure_box(player_id, box_id, box_blob):
    db.execute(
        "INSERT OR REPLACE INTO treasure_box (player_id, box_id, box_blob) VALUES (?, ?, ?)",
        (player_id, box_id, box_blob),
    )


def get_life(player_id, life_index=None):
    cur = db.execute(
        "SELECT life_blob FROM life_info WHERE player_id=?",
        (player_id,),
    )
    row = cur.fetchone()
    if row:
        if life_index:
            return pickle.loads(row[0])[life_index]
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
        if row:
            return pickle.loads(row[0])
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
