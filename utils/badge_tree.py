"""星云树节点奖励与激活互斥。"""

import threading

from config import Config

_activation_locks = {}


def activation_lock(player_id):
    return _activation_locks.setdefault(player_id, threading.Lock())


def rewards(page, box_id):
    return Config.BADGE_NODE_REWARDS.get(page, {}).get(box_id, ())
