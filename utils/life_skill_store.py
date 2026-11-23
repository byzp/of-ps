# 生活技能等级持久化层
# 已迁移到 utils/db.py 的 player_kv 表, 服务器重启不丢失

import utils.db as db


def get_skills(player_id, life_type):
    """返回该玩家该生活类型的技能字典"""
    skills = db.get_life_skills(player_id, life_type)
    if skills is None:
        skills = {}
    return skills


def set_skills(player_id, life_type, skills):
    """持久化技能数据"""
    db.set_life_skills(player_id, life_type, skills)
