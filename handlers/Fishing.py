import random
import threading
import uuid

from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import (
    FishingReq,
    FishingResultNotice,
    FishingRsp,
    LifeBaseInfo,
    LifeProficiencyNotice,
    LifeType,
    PackNotice,
    StatusCode,
)
import utils.db as db
from utils import achieve_track, item_mgr, life_achieve
from utils.pb_create import make_Achieve
from utils.res_loader import res


def _rows(sheet, table):
    section = res.get(sheet, {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def _fishing_level(player_id):
    blob = db.get_life(player_id, LifeType.LIFE_TYPE_Fishing)
    if blob:
        info = LifeBaseInfo()
        info.ParseFromString(blob)
        return max(info.level, 1)
    return 1


def _cast_cost(level):
    row = next((row for row in _rows("Fishing", "fishing_level") if row.get("i_d") == level), None)
    if row is None:
        raise item_mgr.EconomyConfigError("missing fishing level config")
    return row.get("need_item_i_d", 0), row.get("need_item_count", 0)


def _validated_cast(level):
    cost_item, cost_count = _cast_cost(level)
    item_mgr.validate_stackable_item_id(cost_item)
    item_mgr.validate_counter(cost_count, allow_zero=False, label="fishing cost")
    events = _rows("Fishing", "fishing_event")
    fish_rows = _rows("Fishing", "fishing_info")
    if not fish_rows:
        raise item_mgr.EconomyConfigError("missing fishing pool")
    for event in events:
        item_mgr.validate_counter(event.get("i_d", 0), allow_zero=False, label="fishing event id")
        for choice in event.get("fishing_event_items") or ():
            item_mgr.validate_counter(choice.get("index", 0), allow_zero=False, label="fishing event index")
    candidates = [
        row for row in fish_rows
        if row.get("is_show") and int(row.get("need_level", 1)) <= level
    ]
    for fish in candidates:
        item_mgr.validate_item_id(fish.get("i_d"))
        minimum = int(fish.get("min_size", 1))
        maximum = int(fish.get("max_size", 200))
        item_mgr.validate_count(minimum, label="minimum fish size")
        item_mgr.validate_count(maximum, label="maximum fish size")
        if minimum > maximum:
            raise item_mgr.EconomyConfigError("invalid fish size range")
    return cost_item, cost_count, events, candidates


@packet_handler(MsgId.FishingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FishingReq()
        req.ParseFromString(data)
        if req.is_cancel:
            self._cancel(session, packet_id)
            return
        if not getattr(session, "running", True):
            rsp = FishingRsp(status=StatusCode.StatusCode_BAD_REQ)
            session.send(MsgId.FishingRsp, rsp, packet_id)
            return
        try:
            level = _fishing_level(session.player_id)
            cost_item, cost_count, events, candidates = _validated_cast(level)
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            session.send(MsgId.FishingRsp, FishingRsp(status=StatusCode.StatusCode_CFG_NOT_FOUND), packet_id)
            return

        rsp = FishingRsp()
        result = rsp.fishing_event_result
        result.cost_endurance = cost_count
        result.cost_time = random.randint(3, 20)
        remaining = result.cost_time
        while remaining > 1 and events:
            event = result.fishing_event_list.add()
            config = random.choice(events)
            event.i_d = config["i_d"]
            choices = config.get("fishing_event_items") or ()
            if choices:
                event.index = random.choice(choices)["index"]
            remaining -= 5
        fish_id = 0
        fish_info = None
        if random.random() < 0.5 and candidates:
            fish_info = random.choice(candidates)
            fish_id = fish_info["i_d"]
            fish = result.fish_infos.add()
            fish.i_d = fish_id
            fish.length = random.uniform(fish_info.get("min_size", 1), fish_info.get("max_size", 200))

        token = uuid.uuid4().hex
        cost_pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with item_mgr.player_lock(session.player_id):
                if getattr(session, "fishing", False):
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                elif not item_mgr.consume_items(
                    session.player_id,
                    [(cost_item, cost_count)],
                    pack_notice=cost_pack,
                    session=session,
                ):
                    rsp.status = StatusCode.StatusCode_EnergyNotEnough
                else:
                    session.fishing = True
                    session.fishing_token = token
                    session.fishing_cost = (cost_item, cost_count)
                    try:
                        timer = threading.Timer(result.cost_time, lambda: self._finish(session, token, fish_id, fish_info))
                        timer.daemon = True
                        timer.start()
                    except Exception:
                        item_mgr.grant_items(
                            session.player_id,
                            [(cost_item, cost_count)],
                            pack_notice=cost_pack,
                            session=session,
                        )
                        session.fishing = False
                        session.fishing_token = ""
                        session.fishing_cost = None
                        raise
                    rsp.status = StatusCode.StatusCode_OK
                    rsp.is_cancel = False
        except Exception:
            session.fishing = False
            session.fishing_token = ""
            raise
        session.send(MsgId.FishingRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and cost_pack.items:
            session.send(MsgId.PackNotice, cost_pack, 0)

    @staticmethod
    def _cancel(session, packet_id):
        rsp = FishingRsp(status=StatusCode.StatusCode_OK, is_cancel=True)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        with item_mgr.player_lock(session.player_id):
            token = getattr(session, "fishing_token", "")
            cost = getattr(session, "fishing_cost", None)
            if token and cost:
                cost_item, cost_count = cost
                item_mgr.grant_items(
                    session.player_id,
                    [(cost_item, cost_count)],
                    pack_notice=pack,
                    session=session,
                )
            session.fishing = False
            session.fishing_token = ""
            session.fishing_cost = None
        session.send(MsgId.FishingRsp, rsp, packet_id)
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)

    @staticmethod
    def _finish(session, token, fish_id, fish_info):
        notice = FishingResultNotice(status=StatusCode.StatusCode_OK)
        proficiency = None
        failed_config = False
        with item_mgr.player_lock(session.player_id), db.transaction():
            if getattr(session, "fishing_token", "") != token:
                return
            if not getattr(session, "running", True):
                cost_item, cost_count = session.fishing_cost
                item_mgr.grant_items(session.player_id, [(cost_item, cost_count)])
                session.fishing = False
                session.fishing_token = ""
                session.fishing_cost = None
                return
            try:
                if fish_id:
                    blob = db.get_life(session.player_id, LifeType.LIFE_TYPE_Fishing)
                    life = LifeBaseInfo()
                    if blob:
                        life.ParseFromString(blob)
                        # 先验证 uint32 生活经验, 再发鱼; 避免失败补偿时鱼已入库。
                        life.proficiency_value = item_mgr.checked_add(
                            life.proficiency_value, 10, limit=Config.ECONOMY_UINT32_MAX
                        )
                    item_mgr.grant_items(session.player_id, [(fish_id, 1)], pack_notice=notice, session=session)
                    if blob:
                        db.set_life(session.player_id, LifeType.LIFE_TYPE_Fishing, life.SerializeToString())
                        proficiency = life.proficiency_value
                session.fishing = False
                session.fishing_token = ""
                session.fishing_cost = None
            except item_mgr.EconomyConfigError:
                # 发奖配置/数量异常时退还本轮精力, 不留下已结束但无法领取的预订。
                cost_item, cost_count = session.fishing_cost
                item_mgr.grant_items(session.player_id, [(cost_item, cost_count)], pack_notice=notice)
                session.fishing = False
                session.fishing_token = ""
                session.fishing_cost = None
                notice.status = StatusCode.StatusCode_CFG_NOT_FOUND
                failed_config = True
        if failed_config:
            session.send(MsgId.FishingResultNotice, notice, 0)
            return
        if fish_id:
            make_Achieve(session, fish_id)
            if proficiency is not None:
                proficiency_notice = LifeProficiencyNotice(status=StatusCode.StatusCode_OK)
                proficiency_notice.life_proficiency.life_type = LifeType.LIFE_TYPE_Fishing
                proficiency_notice.life_proficiency.proficiency_value = proficiency
                session.send(MsgId.LifeProficiencyNotice, proficiency_notice, 0)
                life_achieve.notify(session, LifeType.LIFE_TYPE_Fishing)
            achieve_track.report(session, "fish", fish=fish_id, day=(fish_info or {}).get("new_day_type"), classify=(fish_info or {}).get("new_fish_classify_type"))
        else:
            achieve_track.report(session, "fish_fail")
        session.send(MsgId.FishingResultNotice, notice, 0)
