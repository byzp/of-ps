"""战令(BattlePass)经验/等级 —— 薄封装, 统一委托 utils/db.py。

历史双轨(battle_pass_exp vs battle_pass)已收敛到 player_kv ns=battle_pass,
真实经验曲线见 db._bp_*。
"""

import utils.db as db


def add_exp(player_id, battle_pass_id, exp):
    return db.bp_add_exp(player_id, battle_pass_id, exp)


def get_exp(player_id, battle_pass_id):
    return db.bp_get_exp(player_id, battle_pass_id)
