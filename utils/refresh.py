"""过期对象与每日重置的惰性刷新助手。"""

from config import Config

import time

from utils.res_loader import res


def day_index(now=None):
    """当前游戏日序号(以凌晨 4 点为界)"""
    dt = time.localtime(now if now is not None else time.time())
    days = (
        int(time.mktime((dt.tm_year, dt.tm_mon, dt.tm_mday, 0, 0, 0, 0, 0, 0))) // 86400
    )
    return days if dt.tm_hour >= Config.DAY_RESET_HOUR else days - 1


def moon_spot_ttl_ms():
    """祈愿石信标存活期 MoonSpot.moon_spot.recycle_seconds"""
    row = res["MoonSpot"]["moon_spot"]["datas"][0]
    return int(row.get("recycle_seconds", 3600)) * 1000
