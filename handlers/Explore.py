import pickle as _pk
import time as _t

from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ExploreReq, ExploreRsp, PackNotice, StatusCode
import utils.db as db
import utils.garden_state as garden_state
from utils import item_mgr
from utils.res_loader import res


def _rows(sheet, table):
    section = res.get(sheet, {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def activity_config(explore_id):
    return next(
        (row for row in _rows("Explore", "explore_activity") if row.get("i_d") == explore_id),
        None,
    )


def _item_rewards(entries):
    rewards = []
    for entry in entries or ():
        item_id = int(entry.get("rewar_item_i_d", 0) or 0)
        if not item_id:
            raise item_mgr.EconomyConfigError("missing explore reward item")
        rewards.append((item_id, 1))
    if not rewards:
        raise item_mgr.EconomyConfigError("empty explore reward list")
    item_mgr.validate_rewards(rewards)
    return rewards


def activity_rewards(cfg):
    rewards = []
    special = int(cfg.get("special_reward_item_i_d", 0) or 0)
    if special:
        rewards.append((special, 1))
    entries = cfg.get("explore_activity_item", ()) or ()
    if entries:
        rewards.extend(_item_rewards(entries))
    if not rewards:
        raise item_mgr.EconomyConfigError("empty explore reward list")
    item_mgr.validate_rewards(rewards)
    return rewards


def area_rewards(explore_id):
    cfg = garden_state.explore_area_cfg(explore_id)
    if cfg is None:
        raise item_mgr.EconomyConfigError("missing explore area config")
    return _item_rewards(cfg.get("explore_area_item", ()))


def validate_quick_cost(cfg):
    item_id = int(cfg.get("quick_need_item", 0) or 0)
    count = int(cfg.get("quick_need_item_count", 0) or 0)
    item_mgr.validate_stackable_item_id(item_id)
    item_mgr.validate_count(count, label="explore quick-finish cost")
    return item_id, count


def validate_duration(cfg):
    duration = int(cfg.get("need_time", 0) or 0)
    item_mgr.validate_count(duration, label="explore duration")
    return duration


def _default_activity_state():
    return {"times": 0, "start_time": 0, "is_quick_finish": False, "collectable": False}


def load_activity_state(player_id, key):
    """读取并校验活动探索状态; 损坏或负数字段按配置错误拒绝。"""
    raw = db.get_kv(player_id, "activity_explore", key, b"")
    try:
        state = _pk.loads(raw) if raw else {}
    except (_pk.UnpicklingError, EOFError, AttributeError, ImportError, IndexError) as exc:
        raise item_mgr.EconomyConfigError("corrupt activity explore state") from exc
    if not isinstance(state, dict):
        raise item_mgr.EconomyConfigError("invalid activity explore state")
    state = dict(state)
    state["times"] = item_mgr.validate_counter(
        int(state.get("times", 0)), label="explore times"
    )
    state["start_time"] = item_mgr.validate_counter(
        int(state.get("start_time", 0) or 0), label="explore start time"
    )
    for field in ("is_quick_finish", "collectable"):
        value = state.get(field, False)
        if not isinstance(value, bool):
            raise item_mgr.EconomyConfigError("invalid explore state flag")
        state[field] = value
    return state


def save_activity_state(player_id, key, state):
    db.set_kv(player_id, "activity_explore", key, _pk.dumps(state))


def load_area_state(player_id, explore_id):
    try:
        state = garden_state.get_explore(player_id, explore_id)
    except (_pk.UnpicklingError, EOFError, AttributeError, ImportError, IndexError) as exc:
        raise item_mgr.EconomyConfigError("corrupt area explore state") from exc
    if not isinstance(state, dict):
        raise item_mgr.EconomyConfigError("invalid area explore state")
    state = dict(state)
    state["times"] = item_mgr.validate_counter(
        int(state.get("times", 0)), label="explore times"
    )
    state["start_time"] = item_mgr.validate_count(
        int(state.get("start_time", 0) or 0),
        allow_zero=True,
        label="explore start time",
    )
    for field in ("is_quick_finish", "collect_reward"):
        value = state.get(field, False)
        if not isinstance(value, bool):
            raise item_mgr.EconomyConfigError("invalid explore state flag")
        state[field] = value
    return state


def save_area_state(player_id, explore_id, state):
    garden_state.set_explore(player_id, explore_id, state)


@packet_handler(MsgId.ExploreReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreReq()
        req.ParseFromString(data)
        rsp = ExploreRsp(is_activity=req.is_activity)
        try:
            if req.is_activity:
                pack = self._start_activity(session, req, rsp)
            else:
                pack = self._start_area(session, req, rsp)
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            pack = None
        session.send(MsgId.ExploreRsp, rsp, packet_id)
        if pack is not None and pack.items:
            session.send(MsgId.PackNotice, pack, 0)

    @staticmethod
    def _start_activity(session, req, rsp):
        cfg = activity_config(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            return
        validate_duration(cfg)
        validate_quick_cost(cfg)
        activity_rewards(cfg)
        max_times = item_mgr.validate_counter(
            int(cfg.get("max_times", 0) or 0), allow_zero=True, label="explore limit"
        )
        key = str(cfg["i_d"])
        with (
            item_mgr.player_lock(session.player_id),
            item_mgr.deferred_notifications(),
            db.transaction(),
        ):
            state = load_activity_state(session.player_id, key)
            times = state["times"]
            start = state["start_time"]
            if start:
                rsp.status = StatusCode.StatusCode_EXPLORE_IN_PROGRESS
            elif max_times and times >= max_times:
                rsp.status = StatusCode.StatusCode_EXPLORE_NUM_LIMIT
            else:
                state.update(
                    start_time=int(_t.time()),
                    is_quick_finish=False,
                    times=item_mgr.checked_add(
                        times, 1, limit=Config.ECONOMY_UINT32_MAX
                    ),
                    collectable=False,
                )
                save_activity_state(session.player_id, key, state)
                rsp.status = StatusCode.StatusCode_OK
                info = rsp.explore
                info.explore_id = cfg["i_d"]
                info.times = state["times"]
                info.start_time = state["start_time"]

    @staticmethod
    def _start_area(session, req, rsp):
        cfg = garden_state.explore_area_cfg(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            return
        validate_duration(cfg)
        validate_quick_cost(cfg)
        area_rewards(req.explore_id)
        need_level = item_mgr.validate_counter(
            int(cfg.get("need_player_level", 0) or 0),
            allow_zero=True,
            label="explore level requirement",
        )
        need_item = int(cfg.get("need_item", 0) or 0)
        need_count = int(cfg.get("need_item_count", 0) or 0)
        if bool(need_item) != bool(need_count):
            raise item_mgr.EconomyConfigError("incomplete explore entry requirement")
        if need_item:
            item_mgr.validate_stackable_item_id(need_item)
            item_mgr.validate_count(need_count, label="explore entry cost")
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        with (
            item_mgr.player_lock(session.player_id),
            item_mgr.deferred_notifications(),
            db.transaction(),
        ):
            level_row = db.get_players_info(session.player_id, "level")
            level = int(level_row[0] or 0) if level_row else 0
            if need_level and level < need_level:
                rsp.status = StatusCode.StatusCode_PLAYER_LEVEL_LIMIT
                return
            state = load_area_state(session.player_id, req.explore_id)
            if int(state.get("start_time", 0) or 0):
                rsp.status = StatusCode.StatusCode_EXPLORE_IN_PROGRESS
                garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
                return
            if need_item and not item_mgr.consume_items(
                session.player_id,
                [(need_item, need_count)],
                pack_notice=pack,
                session=session,
            ):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
                return pack
            state["start_time"] = garden_state.now_ms()
            state["is_quick_finish"] = False
            save_area_state(session.player_id, req.explore_id, state)
            rsp.status = StatusCode.StatusCode_OK
            garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
            return pack
