import sqlite3
import time
import os
import logging
from config import Config

logger = logging.getLogger(__name__)

if not os.path.exists(Config.DB_PATH):
    logger.warning("database not exists!")
    db = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS id_maps (
           sdk_uid INTEGER PRIMARY KEY,
           user_id INTEGER UNIQUE
        );
        INSERT INTO id_maps (sdk_uid ,user_id) VALUES (123, 10000000);
        """
    )
else:
    db = sqlite3.connect(Config.DB_PATH, check_same_thread=False)


def get_user_id(sdk_uid):
    return 9253086
    cur = db.execute("SELECT user_id FROM id_maps WHERE sdk_uid=?;", (sdk_uid,))
    row = cur.fetchone()

    if row is not None:
        return int(row[0])
    cur = db.execute("SELECT MAX(user_id) FROM id_maps;")
    user_id = int(cur.fetchone()[0]) + 1
    db.execute(
        "INSERT INTO id_maps (sdk_uid ,user_id) VALUES (?, ?);",
        (
            sdk_uid,
            user_id,
        ),
    )
    return user_id


def get_player_id(user_id):
    return user_id


def get_register_time(user_id):
    return 1760101000


def get_region_name(user_id):
    return "cn_prod_main"


def get_analysis_account_id(user_id):
    return str(user_id)


def get_player_name(user_id):
    return "Vexuro."


def get_client_log_server_token(user_id):
    return "dG9rZW4="


def get_server_time_zone(user_id):
    return 8 * 3600


def get_unlock_functions(user_id):
    return [
        100000009,
        100000003,
        100000021,
        100000006,
        100000044,
        100000031,
        # 100000045,
        # 100000046,
    ]


def get_level(user_id):
    return 6


def get_exp(user_id):
    return 200


def get_head(user_id):
    return 41101


def get_phone_background(user_id):
    return 8000


def get_create_time(user_id):
    return 1760101000


def get_SupplyBox_next_reward_time(user_id):
    return int(time.time() + 3600)


def get_garden_info(user_id):
    return 0, 0, 0, 50000, True


def get_characters(user_id):
    a = []
    b = []
    from utils.res_loader import res

    for i in res["Character"]["character"]["datas"]:
        b.append(i["i_d"])
    for i in b:
        a.append(
            {
                "character_id": i,
                "level": 1,
                "max_level": 20,
                "equipment_presets": [
                    {"weapon": 32},
                    {"preset_index": 1},
                    {"preset_index": 2},
                ],
                "outfit_presets": [
                    {"hair": 4041012, "clothes": 4041013},  # ? "10": ""
                    {"preset_index": 1, "hair": 4041012, "clothes": 4041013},
                    {"preset_index": 2, "hair": 4041012, "clothes": 4041013},
                ],
                "character_appearance": {
                    "badge": 5000,
                    "umbrella_id": 4050,
                    "logging_axe_instance_id": 33,
                },
                "character_skill_list": [
                    {"skill_id": 4010400, "skill_level": 1},
                    {"skill_id": 4010410, "skill_level": 1},
                    {"skill_id": 4030230, "skill_level": 1},
                ],
            }
        )
    return a


def get_month_card_over_due_time(user_id):
    return 1744664399


def get_month_card_reward_days(user_id):
    return 3


def get_birthday(user_id):
    return "1992-02-25"


def get_account_type(user_id):
    return 9999


def get_team(user_id):
    return 101001, 202002, 202004


def get_items(user_id):
    from utils.res_loader import res
    from proto import OverField_pb2

    rsp = OverField_pb2.PackNotice()
    rsp.status = 1
    for i in res["Item"]["item"]["datas"]:
        tmp = rsp.items.add().main_item
        tmp.item_id = i["i_d"]
        tmp.item_tag = i["new_bag_item_tag"]
        tmp.base_item.item_id = i["i_d"]
        tmp.base_item.num = 10
    rsp.temp_pack_max_size = 30
    return rsp.SerializeToString()
