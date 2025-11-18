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
        CREATE TABLE IF NOT EXISTS id_maps (
           sdk_uid INTEGER PRIMARY KEY,
           user_id INTEGER UNIQUE
        );
        
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
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
            user_id INTEGER PRIMARY KEY,
            over_due_time INTEGER DEFAULT 0,
            reward_days INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        
        CREATE TABLE IF NOT EXISTS supply_box (
            user_id INTEGER PRIMARY KEY,
            next_reward_time INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        
        CREATE TABLE IF NOT EXISTS garden_info (
            user_id INTEGER PRIMARY KEY,
            field1 INTEGER DEFAULT 0,
            field2 INTEGER DEFAULT 0,
            field3 INTEGER DEFAULT 0,
            field4 INTEGER DEFAULT 50000,
            field5 INTEGER DEFAULT 1,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            character_id INTEGER,
            level INTEGER DEFAULT 1,
            max_level INTEGER DEFAULT 20,
            exp INTEGER DEFAULT 200,
            star INTEGER DEFAULT 2,
            equipment_presets BLOB,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        
        CREATE TABLE IF NOT EXISTS items (
            user_id INTEGER,
            item_data BLOB,
            PRIMARY KEY(user_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        
        CREATE TABLE IF NOT EXISTS chat_history (
            user_id INTEGER,
            history_data BLOB,
            PRIMARY KEY(user_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        
        CREATE TABLE IF NOT EXISTS character_equip (
            user_id INTEGER,
            character_id INTEGER,
            equipment_preset BLOB,
            PRIMARY KEY(user_id, character_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS sdk_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            user_token TEXT NOT NULL
        );
        
        INSERT INTO id_maps (sdk_uid, user_id) VALUES (123, 10000000);
        """
    )
    db.commit()
else:
    db = sqlite3.connect(Config.DB_PATH, check_same_thread=False)


def init_user(user_id):
    """初始化新用户数据"""
    cur_time = int(time.time())
    player_name = str(user_id)
    # 初始化用户基本信息
    unlock_funcs = pickle.dumps(
        [100000009, 100000003, 100000021, 100000006, 100000044, 100000031]
    )
    team = pickle.dumps((101001, 202002, 202004))

    db.execute(
        """INSERT OR IGNORE INTO users 
        (user_id, player_name, register_time, create_time, unlock_functions, team) 
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, player_name, cur_time, cur_time, unlock_funcs, team),
    )

    # 初始化月卡
    db.execute(
        "INSERT OR IGNORE INTO month_card (user_id, over_due_time, reward_days) VALUES (?, ?, ?)",
        (user_id, 1744664399, 3),
    )

    # 初始化补给箱
    db.execute(
        "INSERT OR IGNORE INTO supply_box (user_id, next_reward_time) VALUES (?, ?)",
        (user_id, int(time.time() + 3600)),
    )

    # 初始化花园
    db.execute("INSERT OR IGNORE INTO garden_info (user_id) VALUES (?)", (user_id,))

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
                (user_id, character_id, equipment_presets) VALUES (?, ?, ?)""",
                (user_id, i["i_d"], equipment_presets),
            )

    # 初始化物品
    from proto import OverField_pb2

    rsp = OverField_pb2.PackNotice()
    rsp.status = 1
    for i in res["Item"]["item"]["datas"]:
        tmp = rsp.items.add().main_item
        tmp.item_id = i["i_d"]
        tmp.item_tag = i["new_bag_item_tag"]
        tmp.base_item.item_id = i["i_d"]
        if i["i_d"] == 102:
            tmp.base_item.num = 2147483647
        else:
            tmp.base_item.num = 10
    rsp.temp_pack_max_size = 30

    db.execute(
        "INSERT OR IGNORE INTO items (user_id, item_data) VALUES (?, ?)",
        (user_id, rsp.SerializeToString()),
    )

    # 初始化聊天记录
    chat_data = [
        {"type": 0, "msg": []},
        {"type": 1, "msg": []},
        {"type": 2, "msg": []},
        {"type": 3, "msg": []},
    ]
    db.execute(
        "INSERT OR IGNORE INTO chat_history (user_id, history_data) VALUES (?, ?)",
        (user_id, pickle.dumps(chat_data)),
    )

    db.commit()


def verify_sdk_user_info(sdk_uid, login_token):
    return True
    cur = db.execute(
        "SELECT id, username, user_token FROM sdk_users WHERE id = ? AND user_token = ?",
        (
            sdk_uid,
            login_token,
        ),
    )
    row = cur.fetchone()
    if row:
        return True
    return False


def get_sdk_user_info(username, password):

    cur = db.execute(
        "SELECT id, username, user_token FROM sdk_users WHERE username = ?",
        (username,),
    )
    row = cur.fetchone()
    if row:
        if row[1] == password:
            return {"id": row[0], "username": row[1], "user_token": row[2]}
        else:
            return None
    else:

        auth_token = secrets.token_hex(16)
        cur = db.execute(
            "INSERT INTO sdk_users (username, password, user_token) VALUES (?, ?, ?)",
            (username, password, auth_token),
        )
        return {
            "id": get_user_id(0),
            "username": username,
            "user_token": auth_token,
        }


iii = 9253195


def get_user_id(sdk_uid):
    global iii
    iii += 1
    return iii
    cur = db.execute("SELECT user_id FROM id_maps WHERE sdk_uid=?;", (sdk_uid,))
    row = cur.fetchone()

    if row is not None:
        return int(row[0])

    cur = db.execute("SELECT MAX(user_id) FROM id_maps;")
    max_id = cur.fetchone()[0]
    user_id = int(max_id) + 1 if max_id else 10000000

    db.execute(
        "INSERT INTO id_maps (sdk_uid, user_id) VALUES (?, ?);", (sdk_uid, user_id)
    )
    db.commit()

    # 初始化新用户
    init_user(user_id)

    return user_id


def get_player_id(user_id):
    return user_id


def get_register_time(user_id):
    cur = db.execute("SELECT register_time FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return int(row[0] if row else int(time.time()))


def get_region_name(user_id):
    cur = db.execute("SELECT region_name FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else "cn_prod_main"


def get_analysis_account_id(user_id):
    return str(user_id)


def get_player_name(user_id):
    cur = db.execute("SELECT player_name FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else "Vexuro."


def set_player_name(user_id, name):
    db.execute("UPDATE users SET player_name=? WHERE user_id=?", (name, user_id))
    db.commit()


def get_client_log_server_token(user_id):
    cur = db.execute(
        "SELECT client_log_server_token FROM users WHERE user_id=?", (user_id,)
    )
    row = cur.fetchone()
    return row[0] if row else "dG9rZW4="


def get_server_time_zone(user_id):
    cur = db.execute("SELECT server_time_zone FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 8 * 3600


def get_unlock_functions(user_id):
    cur = db.execute("SELECT unlock_functions FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row and row[0]:
        return pickle.loads(row[0])
    return [100000009, 100000003, 100000021, 100000006, 100000044, 100000031]


def set_unlock_functions(user_id, functions):
    db.execute(
        "UPDATE users SET unlock_functions=? WHERE user_id=?",
        (pickle.dumps(functions), user_id),
    )
    db.commit()


def get_level(user_id):
    cur = db.execute("SELECT level FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 6


def set_level(user_id, level):
    db.execute("UPDATE users SET level=? WHERE user_id=?", (level, user_id))
    db.commit()


def get_exp(user_id):
    cur = db.execute("SELECT exp FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 200


def set_exp(user_id, exp):
    db.execute("UPDATE users SET exp=? WHERE user_id=?", (exp, user_id))
    db.commit()


def get_avatar(user_id):  # head 头像
    cur = db.execute("SELECT head FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 41101


def set_avatar(user_id, head):
    db.execute("UPDATE users SET head=? WHERE user_id=?", (head, user_id))
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


def get_phone_background(user_id):
    cur = db.execute("SELECT phone_background FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 8000


def set_phone_background(user_id, background):
    db.execute(
        "UPDATE users SET phone_background=? WHERE user_id=?", (background, user_id)
    )
    db.commit()


def get_create_time(user_id):
    cur = db.execute("SELECT create_time FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else int(time.time())


def get_SupplyBox_next_reward_time(user_id):
    cur = db.execute(
        "SELECT next_reward_time FROM supply_box WHERE user_id=?", (user_id,)
    )
    row = cur.fetchone()
    return row[0] if row else int(time.time() + 3600)


def set_SupplyBox_next_reward_time(user_id, next_time):
    db.execute(
        "INSERT OR REPLACE INTO supply_box (user_id, next_reward_time) VALUES (?, ?)",
        (user_id, next_time),
    )
    db.commit()


def get_garden_info(user_id):
    cur = db.execute(
        "SELECT field1, field2, field3, field4, field5 FROM garden_info WHERE user_id=?",
        (user_id,),
    )
    row = cur.fetchone()
    if row:
        return row[0], row[1], row[2], row[3], bool(row[4])
    return 0, 0, 0, 50000, True


def set_garden_info(user_id, field1, field2, field3, field4, field5):
    db.execute(
        """INSERT OR REPLACE INTO garden_info 
        (user_id, field1, field2, field3, field4, field5) VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, field1, field2, field3, field4, int(field5)),
    )
    db.commit()


def get_characters(user_id):
    # cur = db.execute(
    #     """SELECT character_id, level, max_level, exp, star, equipment_presets
    #     FROM characters WHERE user_id=?""",
    #     (user_id,),
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
        if i["i_d"] in [101001, 102001, 102002, 103002, 201001, 302002, 401001, 403002]:
            pass
        if i.get("ex_spell_i_ds") is None:
            continue
        # if i["i_d"] in [101003,101004,102003,102004,103001,103002,201002,201003,202001,202002,202003,202004,301002,301003,301004,302001,302002,302003,302004,401001,401002,401003,401004,402001,402002,402003,403001,403003,403004]:
        if True:
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


def update_character(user_id, character_id, **kwargs):
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
        values.extend([user_id, character_id])
        db.execute(
            f"UPDATE characters SET {', '.join(fields)} WHERE user_id=? AND character_id=?",
            values,
        )
        db.commit()


def get_month_card_over_due_time(user_id):
    cur = db.execute("SELECT over_due_time FROM month_card WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 0


def set_month_card_over_due_time(user_id, over_due_time):
    db.execute(
        "INSERT OR REPLACE INTO month_card (user_id, over_due_time) VALUES (?, ?)",
        (user_id, over_due_time),
    )
    db.commit()


def get_month_card_reward_days(user_id):
    cur = db.execute("SELECT reward_days FROM month_card WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 0


def set_month_card_reward_days(user_id, reward_days):
    db.execute(
        "UPDATE month_card SET reward_days=? WHERE user_id=?", (reward_days, user_id)
    )
    db.commit()


def get_birthday(user_id):
    cur = db.execute("SELECT birthday FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else "1992-02-25"


def set_birthday(user_id, birthday):
    db.execute("UPDATE users SET birthday=? WHERE user_id=?", (birthday, user_id))
    db.commit()


def get_account_type(user_id):
    cur = db.execute("SELECT account_type FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 9999


def get_team_char_id(user_id):
    cur = db.execute("SELECT team FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row and row[0]:
        return pickle.loads(row[0])
    return [101001, 202002, 202004]


def set_team_char_id(user_id, *character_ids):
    db.execute(
        "UPDATE users SET team=? WHERE user_id=?",
        (pickle.dumps(character_ids), user_id),
    )
    db.commit()


def get_items(user_id):
    cur = db.execute("SELECT item_data FROM items WHERE user_id=?", (user_id,))
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


def set_item(user_id, item_id, num):  # num是数值变化
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


def get_chat_history(user_id):
    cur = db.execute(
        "SELECT history_data FROM chat_history WHERE user_id=?", (user_id,)
    )
    row = cur.fetchone()

    if row and row[0]:
        return pickle.loads(row[0])

    return [
        {"type": 0, "msg": []},
        {"type": 1, "msg": []},
        {"type": 2, "msg": []},
        {"type": 3, "msg": []},
    ]


def add_chat_message(user_id, chat_type, message):
    """添加聊天消息"""
    history = get_chat_history(user_id)

    # 找到对应类型的聊天记录
    for chat in history:
        if chat["type"] == chat_type:
            chat["msg"].append(message)
            break

    db.execute(
        "UPDATE chat_history SET history_data=? WHERE user_id=?",
        (pickle.dumps(history), user_id),
    )
    db.commit()


def get_character_achievement_lst(user_id, chr_id):
    from utils.res_loader import res

    for i in res["Character"]["character_achieve"]["datas"]:
        if i["i_d"] == chr_id:
            return i["achieve_info"]
    return None


def up_character_equip(user_id, chr_id, equipment_preset):
    """更新角色装备"""
    db.execute(
        """INSERT OR REPLACE INTO character_equip 
        (user_id, character_id, equipment_preset) VALUES (?, ?, ?)""",
        (user_id, chr_id, pickle.dumps(equipment_preset)),
    )
    db.commit()


def get_character_equip(user_id, chr_id):
    """获取角色装备"""
    cur = db.execute(
        "SELECT equipment_preset FROM character_equip WHERE user_id=? AND character_id=?",
        (user_id, chr_id),
    )
    row = cur.fetchone()
    if row and row[0]:
        return pickle.loads(row[0])
    return None
