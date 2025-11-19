import sqlite3
import time
import os
import logging
import pickle
import json
from config import Config
import secrets

from utils.res_loader import res
from proto import OverField_pb2

logger = logging.getLogger(__name__)

# 初始化数据库连接
if not os.path.exists(Config.DB_PATH):
    logger.warning("database not exists!")
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
            register_time INTEGER,
            create_time INTEGER,
            region_name TEXT DEFAULT 'cn_prod_main',
            client_log_server_token TEXT DEFAULT 'dG9rZW4=',
            server_time_zone INTEGER DEFAULT 28800,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 200,
            head INTEGER DEFAULT 41101,
            phone_background INTEGER DEFAULT 8000,
            birthday TEXT DEFAULT '1992-02-25',
            account_type INTEGER DEFAULT 9999,
            unlock_functions BLOB,
            team BLOB
        );
        
        CREATE TABLE IF NOT EXISTS month_card (
            player_id INTEGER PRIMARY KEY,
            over_due_time INTEGER DEFAULT 0,
            reward_days INTEGER DEFAULT 0,
            FOREIGN KEY(player_id) REFERENCES players(player_id)
        );
        
        
        CREATE TABLE IF NOT EXISTS garden_info (
            player_id INTEGER PRIMARY KEY,
            like_num INTEGER DEFAULT 0,
            access_num INTEGER DEFAULT 0,
            furniture_num INTEGER DEFAULT 0,
            furniture_limit_num INTEGER DEFAULT 500000,
            is_open INTEGER DEFAULT 1,
            FOREIGN KEY(player_id) REFERENCES players(player_id)
        );
        
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER,
            character_id INTEGER,
            level INTEGER DEFAULT 1,
            max_level INTEGER DEFAULT 20,
            exp INTEGER DEFAULT 200,
            star INTEGER DEFAULT 2,
            equipment_presets BLOB,
            FOREIGN KEY(player_id) REFERENCES players(player_id)
        );
        
        CREATE TABLE IF NOT EXISTS items (
            player_id INTEGER,
            item_data BLOB,
            PRIMARY KEY(player_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id)
        ); 
        
        CREATE TABLE IF NOT EXISTS character_equip (
            player_id INTEGER,
            character_id INTEGER,
            equipment_preset BLOB,
            PRIMARY KEY(player_id, character_id),
            FOREIGN KEY(player_id) REFERENCES players(player_id)
        );

        INSERT INTO users (id, username, password, user_token) VALUES (1000000, "", "", "");

        """
    )
    db.commit()
else:
    db = sqlite3.connect(Config.DB_PATH, check_same_thread=False)


def init_player(player_id):
    """初始化新用户数据"""
    cur_time = int(time.time())
    player_name = ""
    # 初始化用户基本信息
    unlock_funcs = pickle.dumps(
        [100000009, 100000003, 100000021, 100000006, 100000044, 100000031]
    )

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
    from utils.res_loader import res

    for i in res["Character"]["character"]["datas"]:
        if i["i_d"] in [102002, 102001, 401001, 401002, 103002, 302002, 201001, 101001]:
            continue
        if i.get("ex_spell_i_ds") is None:
            continue
        if i["i_d"] in [202004, 202003, 202002, 101002]:
            equipment_presets = pickle.dumps([{"preset_index": 1}, {"preset_index": 2}])
            db.execute(
                """INSERT OR IGNORE INTO characters 
                (player_id, character_id, equipment_presets) VALUES (?, ?, ?)""",
                (player_id, i["i_d"], equipment_presets),
            )

    # 初始化物品

    rsp = OverField_pb2.PackNotice()
    rsp.status = 1
    for i in res["Item"]["item"]["datas"]:
        tmp = rsp.items.add().main_item
        tmp.item_id = i["i_d"]
        tmp.item_tag = i["new_bag_item_tag"]
        tmp.base_item.item_id = i["i_d"]
        tmp.base_item.num = 1000
    rsp.temp_pack_max_size = 30

    db.execute(
        "INSERT OR IGNORE INTO items (player_id, item_data) VALUES (?, ?)",
        (player_id, rsp.SerializeToString()),
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


def get_register_time(player_id):
    cur = db.execute(
        "SELECT register_time FROM players WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return int(row[0] if row else int(time.time()))


def get_region_name(player_id):
    cur = db.execute("SELECT region_name FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    return row[0] if row else "cn_prod_main"


def get_analysis_account_id(player_id):
    return str(player_id)


def get_player_name(player_id):
    cur = db.execute("SELECT player_name FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    return row[0] if row else ""


def set_player_name(player_id, name):
    db.execute("UPDATE players SET player_name=? WHERE player_id=?", (name, player_id))
    db.commit()


def get_client_log_server_token(player_id):
    cur = db.execute(
        "SELECT client_log_server_token FROM players WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return row[0] if row else "dG9rZW4="


def get_server_time_zone(player_id):
    cur = db.execute(
        "SELECT server_time_zone FROM players WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return row[0] if row else 8 * 3600


def get_unlock_functions(player_id):
    cur = db.execute(
        "SELECT unlock_functions FROM players WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    if row and row[0]:
        return pickle.loads(row[0])


def set_unlock_functions(player_id, functions):
    db.execute(
        "UPDATE players SET unlock_functions=? WHERE player_id=?",
        (pickle.dumps(functions), player_id),
    )
    db.commit()


def get_level(player_id):
    cur = db.execute("SELECT level FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    return row[0] if row else 6


def set_level(player_id, level):
    db.execute("UPDATE players SET level=? WHERE player_id=?", (level, player_id))
    db.commit()


def get_exp(player_id):
    cur = db.execute("SELECT exp FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    return row[0] if row else 200


def set_exp(player_id, exp):
    db.execute("UPDATE players SET exp=? WHERE player_id=?", (exp, player_id))
    db.commit()


def get_avatar(player_id):  # head 头像
    cur = db.execute("SELECT head FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    return row[0] if row else 41101


def set_avatar(player_id, head):
    db.execute("UPDATE players SET head=? WHERE player_id=?", (head, player_id))
    db.commit()


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


def get_is_hide_birthday(player_id):
    return False


def set_is_hide_birthday(player_id) -> None:
    pass


def set_sign(player_id, sign: str):
    pass


def get_sign(player_id):
    return ""


def get_phone_background(player_id):
    cur = db.execute(
        "SELECT phone_background FROM players WHERE player_id=?", (player_id,)
    )
    row = cur.fetchone()
    return row[0] if row else 8000


def set_phone_background(player_id, background):
    db.execute(
        "UPDATE players SET phone_background=? WHERE player_id=?",
        (background, player_id),
    )
    db.commit()


def get_create_time(player_id):
    cur = db.execute("SELECT create_time FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    return row[0] if row else int(time.time())


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


def get_characters(player_id):
    # cur = db.execute(
    #     """SELECT character_id, level, max_level, exp, star, equipment_presets
    #     FROM characters WHERE player_id=?""",
    #     (player_id,),
    # )
    # rows = cur.fetchall()

    # characters = []
    # for row in rows:
    #     char_data = {
    #         "character_id": row[0],
    #         "level": row[1],
    #         "max_level": row[2],
    #         "exp": row[3],
    #         "star": row[4],
    #         "equipment_presets": pickle.loads(row[5]) if row[5] else [],
    #     }
    #     characters.append(char_data)

    # return characters
    a = []

    for i in res["Character"]["character"]["datas"]:
        if i.get("ex_spell_i_ds") is None:
            continue
        a.append(
            {
                "character_id": i["i_d"],
                "level": 1,
                "max_level": 20,
                "exp": 200,
                "star": 2,
                "equipment_presets": [
                    # {"weapon": 16},
                    {"preset_index": 1},
                    {"preset_index": 2},
                ],
                "outfit_presets": [
                    {},  # ? "10": ""
                    {
                        "preset_index": 1,
                        "hair": i.get("hair_i_d"),
                        "clothes": i.get("cloth_i_d"),
                    },
                    {
                        "preset_index": 2,
                        "hair": i.get("hair_i_d"),
                        "clothes": i.get("cloth_i_d"),
                    },
                ],
                "character_appearance": {
                    "badge": 5000,
                    "umbrella_id": 4050,
                    "logging_axe_instance_id": 33,
                },
                "character_skill_list": [
                    {"skill_id": i.get("spell_i_ds")[0], "skill_level": 1},
                    {"skill_id": i.get("spell_i_ds")[1], "skill_level": 1},
                    {"skill_id": i.get("ex_spell_i_ds")[0], "skill_level": 1},
                ],
            }
        )
    return a


def update_character(player_id, character_id, **kwargs):
    """更新角色信息"""
    fields = []
    values = []

    for key, value in kwargs.items():
        if key == "equipment_presets":
            fields.append(f"{key}=?")
            values.append(pickle.dumps(value))
        else:
            fields.append(f"{key}=?")
            values.append(value)

    if fields:
        values.extend([player_id, character_id])
        db.execute(
            f"UPDATE characters SET {', '.join(fields)} WHERE player_id=? AND character_id=?",
            values,
        )
        db.commit()


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


def get_birthday(player_id):
    cur = db.execute("SELECT birthday FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    return row[0] if row else "1992-02-25"


def set_birthday(player_id, birthday):
    db.execute("UPDATE players SET birthday=? WHERE player_id=?", (birthday, player_id))
    db.commit()


def get_account_type(player_id):
    cur = db.execute("SELECT account_type FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    return row[0] if row else 9999


def get_team_char_id(player_id):
    cur = db.execute("SELECT team FROM players WHERE player_id=?", (player_id,))
    row = cur.fetchone()
    if row and row[0]:
        return pickle.loads(row[0])
    return [101001, 202002, 202004]


def set_team_char_id(player_id, *character_ids):
    db.execute(
        "UPDATE players SET team=? WHERE player_id=?",
        (pickle.dumps(character_ids), player_id),
    )
    db.commit()


def get_items(player_id):
    cur = db.execute("SELECT item_data FROM items WHERE player_id=?", (player_id,))
    row = cur.fetchone()

    if row and row[0]:
        return row[0]

    # 如果没有数据，生成默认物品

    rsp = OverField_pb2.PackNotice()
    rsp.status = 1  # ok
    for i in res["Item"]["item"]["datas"]:
        tmp = rsp.items.add().main_item
        tmp.item_id = i["i_d"]
        tmp.item_tag = i["new_bag_item_tag"]
        tmp.base_item.item_id = i["i_d"]
        tmp.base_item.num = 100
    rsp.temp_pack_max_size = 300

    return rsp.SerializeToString()


def set_item(player_id, item_id, num):  # num是数值变化
    rsp = OverField_pb2.PackNotice()
    rsp.status = 1
    for i in res["Item"]["item"]["datas"]:
        if item_id == i["i_d"]:
            tmp = rsp.items.add().main_item
            tmp.item_id = i["i_d"]
            tmp.item_tag = i["new_bag_item_tag"]
            tmp.base_item.item_id = i["i_d"]
            tmp.base_item.num = 100
            break
    rsp.temp_pack_max_size = 300

    return tmp.SerializeToString()


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


def up_character_equip(player_id, chr_id, equipment_preset):
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
