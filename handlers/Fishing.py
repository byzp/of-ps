from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import random
import threading
import time

from proto.net_pb2 import (
    FishingReq,
    FishingRsp,
    StatusCode,
    FishingResultNotice,
    LifeBaseInfo,
    LifeProficiencyNotice,
    LifeType,
)

import utils.db as db
import utils.life_achieve as life_achieve
from utils import item_mgr
from utils.res_loader import res
from utils import achieve_track
from utils.pb_create import make_Achieve


def _fishing_level(player_id):
    life_blob = db.get_life(player_id, LifeType.LIFE_TYPE_Fishing)
    if life_blob:
        info = LifeBaseInfo()
        info.ParseFromString(life_blob)
        return max(info.level, 1)
    return 1


def _cast_cost(level):
    """每次垂钓消耗查 Fishing.fishing_level(i_d=垂钓等级) 的
    need_item_i_d/need_item_count(全表 1~10 级均为精力11 x1)"""
    for e in res["Fishing"]["fishing_level"]["datas"]:
        if e.get("i_d") == level:
            return (
                e.get("need_item_i_d", Config.FISHING_COST_ITEM_FALLBACK),
                e.get("need_item_count", Config.FISHING_COST_COUNT_FALLBACK),
            )
    return Config.FISHING_COST_ITEM_FALLBACK, Config.FISHING_COST_COUNT_FALLBACK


@packet_handler(MsgId.FishingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FishingReq()
        req.ParseFromString(data)

        rsp = FishingRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.is_cancel = req.is_cancel
        session.fishing = req.is_cancel == 0

        fishing_level = _fishing_level(session.player_id)
        cost_item_id, cost_count = _cast_cost(fishing_level)
        rsp.fishing_event_result.cost_endurance = cost_count
        total_time = random.randint(3, 20)
        rsp.fishing_event_result.cost_time = total_time
        while total_time > 1:
            event = rsp.fishing_event_result.fishing_event_list.add()
            event_s = random.sample(res["Fishing"]["fishing_event"]["datas"], 1)[0]
            event.i_d = event_s["i_d"]
            event.index = random.sample(event_s["fishing_event_items"], 1)[0]["index"]
            total_time -= 5
        has_fish = random.randint(0, 1)
        fish_id = 0
        if (
            has_fish
        ):  # 鱼获计入任务/成就进度(见捕获后 make_Achieve); 额外鱼竿耐久表无配置
            # 鱼按 Fishing.fishing_info 的 need_level<=垂钓等级 且 is_show 过滤,
            # 长度取该鱼 min_size~max_size
            candidates = [
                f
                for f in res["Fishing"]["fishing_info"]["datas"]
                if f.get("is_show") and f.get("need_level", 1) <= fishing_level
            ]
            if not candidates:
                candidates = list(res["Fishing"]["fishing_info"]["datas"])
            fish_s = random.sample(candidates, 1)[0]
            fish_id = fish_s["i_d"]
            fish = rsp.fishing_event_result.fish_infos.add()
            fish.i_d = fish_id
            fish.length = random.uniform(
                fish_s.get("min_size", 1), fish_s.get("max_size", 200)
            )
        session.send(MsgId.FishingRsp, rsp, packet_id)  # 1397,1398

        # 鱼获计入任务/成就进度(条件 param=鱼 id)
        if has_fish:
            make_Achieve(session, fish_id)
            # 成就计数(见 utils/achieve_track 事件层): 成功钓鱼(含昼夜/体型/
            # 鱼获归族)
            info_s = next(
                f
                for f in res["Fishing"]["fishing_info"]["datas"]
                if f["i_d"] == fish_id
            )
            life_blob = db.get_life(session.player_id, LifeType.LIFE_TYPE_Fishing)
            if life_blob:
                life_info = LifeBaseInfo()
                life_info.ParseFromString(life_blob)
                life_info.proficiency_value += 10
                db.set_life(
                    session.player_id,
                    LifeType.LIFE_TYPE_Fishing,
                    life_info.SerializeToString(),
                )
                prof_notice = LifeProficiencyNotice()
                prof_notice.status = StatusCode.StatusCode_OK
                prof_notice.life_proficiency.life_type = LifeType.LIFE_TYPE_Fishing
                prof_notice.life_proficiency.proficiency_value = (
                    life_info.proficiency_value
                )
                session.send(MsgId.LifeProficiencyNotice, prof_notice, 0)
                life_achieve.notify(session, LifeType.LIFE_TYPE_Fishing)
            achieve_track.report(
                session,
                "fish",
                fish=fish_id,
                day=info_s.get("new_day_type"),
                classify=info_s.get("new_fish_classify_type"),
            )
        else:
            achieve_track.report(session, "fish_fail")

        # 等待上钩时间不阻塞包处理队列(否则心跳/其他请求被饿死):
        # FishingRsp 已即时返回, 结果通知按 cost_time 延迟下发
        def _finish():
            time.sleep(rsp.fishing_event_result.cost_time)
            if not session.fishing or session.running is False:
                return
            result = FishingResultNotice()

            # 发放钓到的鱼
            grant_list = []
            if has_fish:
                grant_list.append((fish_id, 1))

            # 扣除精力
            cost_list = [(cost_item_id, cost_count)]

            # 先扣后发, 统一走 items 模块
            item_mgr.consume_items(
                session.player_id,
                cost_list,
                pack_notice=result,
                session=session,
            )
            if grant_list:
                item_mgr.grant_items(
                    session.player_id,
                    grant_list,
                    pack_notice=result,
                    session=session,
                )

            result.status = StatusCode.StatusCode_OK
            session.send(MsgId.FishingResultNotice, result, 0)

        _timer = threading.Timer(rsp.fishing_event_result.cost_time, _finish)
        _timer.daemon = True  # 结果通知为装饰性推送, 不应拖延进程退出/落盘
        _timer.start()
