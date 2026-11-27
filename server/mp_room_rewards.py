import time

from config import Config
from utils import refresh
import utils.db as db

_NAMESPACE = "mp_room_rewards"
_KINDS = ("score", "extra_bonus", "extra_mag")
_PERIODS = ("day", "week")


def period_key(period):
    if period not in _PERIODS:
        raise ValueError("invalid reward period")
    if period == "day":
        return str(refresh.day_index())
    now = time.time() - (0 if time.localtime().tm_hour >= Config.DAY_RESET_HOUR else 86400)
    return time.strftime("%G-W%V", time.localtime(now))


def limit(kind, period):
    if kind not in _KINDS or period not in _PERIODS:
        return 0
    try:
        value = int(Config.MP_ROOM_REWARD_LIMITS[kind][0 if period == "day" else 1])
    except (KeyError, IndexError, TypeError, ValueError):
        return 0
    return max(0, value)


def remaining(player_id, kind, period):
    cap = limit(kind, period)
    if cap <= 0:
        return 0
    used = db.get_kv(player_id, _NAMESPACE, f"{kind}:{period}:{period_key(period)}")
    try:
        used = int(used or 0)
    except (TypeError, ValueError):
        used = 0
    return max(0, cap - max(0, used))


def consume(player_id, kind, period, count=1):
    cap = limit(kind, period)
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0 or count > cap:
        return False
    key = f"{kind}:{period}:{period_key(period)}"
    # transaction 的共享数据库锁串行化读改写，且可与房间结算事务嵌套。
    with db.transaction():
        try:
            used = int(db.get_kv(player_id, _NAMESPACE, key) or 0)
        except (TypeError, ValueError):
            used = 0
        used = max(0, used)
        if used + count > cap:
            return False
        db.set_kv(player_id, _NAMESPACE, key, used + count)
        return True
