import sqlite3
import time
import os
import logging
import pickle
import json
from config import Config
import secrets

from utils.res_loader import res
import proto.OverField_pb2 as Character_pb2
import proto.OverField_pb2 as pb

logger = logging.getLogger(__name__)

db = None


def exit():
    global db
    db.commit()
    if Config.IN_MEMORY:
        disk = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
        db.backup(disk)
        disk.commit()
        disk.close()
    db.close()


def init():
    # 初始化数据库连接
    if not os.path.exists(Config.DB_PATH):
        logger.warning("database not exists!")
    global db
    if Config.IN_MEMORY:
        disk = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
        db = sqlite3.connect(":memory:", check_same_thread=False)
        disk.backup(db)
        disk.close()
    else:
        db = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
    db.executescript(
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
            team_leader_badge INTEGER DEFAULT 0,
            is_online INTEGER DEFAULT 0,
            sign TEXT DEFAULT 'sign',
            guild_name TEXT DEFAULT '',
            character_id INTEGER DEFAULT 0,
            garden_like_num INTEGER DEFAULT 0,
            register_time INTEGER,
            create_time INTEGER,
            region_name TEXT DEFAULT 'cn_prod_main',
            client_log_server_token TEXT DEFAULT 'dG9rZW4=',
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

        INSERT OR IGNORE INTO users (id, username, password, user_token) VALUES (1000000, "", "", "");

    """
    )
    db.commit()


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
        if not i.get("ex_spell_i_ds"):
            continue
        c = Character_pb2.Character()

        c.character_id = i["i_d"]
        c.level = 1
        c.max_level = 20
        c.exp = 200
        c.star = 2

        t1 = c.equipment_presets.add()

        t1.armors.add()
        t1.armors.add().equip_type = pb.EEquipType_Chest
        t1.armors.add().equip_type = pb.EEquipType_Hand
        t1.armors.add().equip_type = pb.EEquipType_Shoes
        t1.posters.add()
        t1.posters.add().poster_index = 1
        t1.posters.add().poster_index = 2

        p = c.equipment_presets.add()
        p.preset_index = 1
        p2 = c.equipment_presets.add()
        p2.preset_index = 2

        o0 = c.outfit_presets.add()
        o0.outfit_hide_info.CopyFrom(pb.OutfitHideInfo())

        o1 = c.outfit_presets.add()
        o1.preset_index = 1
        o1.hair = i.get("hair_i_d")
        o1.clothes = i.get("cloth_i_d")
        o1.outfit_hide_info.CopyFrom(pb.OutfitHideInfo())

        o2 = c.outfit_presets.add()
        o2.preset_index = 2
        o2.hair = i.get("hair_i_d")
        o2.clothes = i.get("cloth_i_d")
        o2.outfit_hide_info.CopyFrom(pb.OutfitHideInfo())

        c.character_appearance.badge = 5000
        c.character_appearance.umbrella_id = 4050
        c.character_appearance.insect_net_instance_id = 0
        c.character_appearance.logging_axe_instance_id = 0
        c.character_appearance.water_bottle_instance_id = 0
        c.character_appearance.mining_hammer_instance_id = 0
        c.character_appearance.collection_gloves_instance_id = 0
        c.character_appearance.fishing_rod_instance_id = 0

        spells = i.get("spell_i_ds", [])
        ex_spells = i.get("ex_spell_i_ds", [])

        s = c.character_skill_list.add()
        s.skill_id = spells[0]
        s.skill_level = 1

        s = c.character_skill_list.add()
        s.skill_id = spells[1]
        s.skill_level = 1

        s = c.character_skill_list.add()
        s.skill_id = ex_spells[0]
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

    db.commit()


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


def get_players_info(player_id, info_name):
    cur = db.execute(f"SELECT {info_name} FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    if row:
        # 如果是BLOB类型字段，需要反序列化
        if info_name in ["team", "unlock_functions"]:
            if row[0]:
                return pickle.loads(row[0])
        return row[0]
    return None


def set_players_info(player_id, info_name, value):
    if info_name in ["team", "unlock_functions"]:
        value = pickle.dumps(value)
    db.execute(
        f"UPDATE players SET {info_name}=? WHERE player_id=?", (value, player_id)
    )
    db.commit()


def get_register_time(player_id):
    cur = db.execute(
        "SELECT register_time FROM players WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return int(row[0] if row else int(time.time()))


def get_analysis_account_id(player_id):
    return str(player_id)


"""
message ChangeHideTypeReq {
    HideType hide_type = 1;
}

message ChangeHideTypeRsp {
    StatusCode status = 1;
    uint32 hide_value = 2;
}

enum HideType {
    TYPE_NONE_none = 0;
    TYPE_NONE_account_type = 1;
    TYPE_NONE_sign_type = 2;
    TYPE_NONE_abyss_rank_type = 4;
}
"""


def get_hide_type(player_id, hide_type) -> bool:
    pass


def set_hide_type(player_id, hide_type) -> bool:
    pass


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
    db.commit()


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
    db.commit()


def get_characters(player_id, character_id=None) -> list:
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
    """更新角色信息"""

    db.execute(
        "INSERT OR REPLACE INTO characters (player_id, character_id, character_blob) VALUES (?, ?, ?)",
        (player_id, character_id, character_blob),
    )
    db.commit()


def get_item_detail(player_id, item_id=None, instance_id=None) -> list:
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


def set_item_detail(player_id, item_detail_blob: list, item_id=None, instance_id=None):
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
    db.commit()


def get_instance_id(player_id):
    cur = db.execute(
        "SELECT MAX(instance_id) AS max_instance_id FROM items_s WHERE player_id=?",
        (player_id,),
    )
    row = cur.fetchone()
    if row[0]:
        return row[0]
    return 1


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
    db.commit()


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
    db.commit()


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
    db.commit()


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
    db.commit()


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
