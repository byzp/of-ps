"""天气计划使用游戏绝对小时，预报与实际天气共用，跨日预报不会重抽。"""

import random

from config import Config
from utils.res_loader import res


def config_int(key, default):
    row = next(
        (
            r
            for r in res.get("GlobalConfig", {}).get("config", {}).get("datas", ())
            if r.get("key") == key
        ),
        None,
    )
    values = row.get("values", ()) if row else ()
    return int(values[0]) if values else default


def weather_at(absolute_hour):
    day, hour = divmod(absolute_hour, 24)
    rain_start = random.Random(f"weather:{day}").randrange(
        25 - Config.WEATHER_RAIN_HOURS
    )
    return int(rain_start <= hour < rain_start + Config.WEATHER_RAIN_HOURS)


def forecast(game_seconds):
    hour = int(game_seconds // 3600)
    hours = config_int("WeatherForecastHour", Config.WEATHER_FORECAST_HOURS)
    return [(value % 24, weather_at(value)) for value in range(hour, hour + hours)]
