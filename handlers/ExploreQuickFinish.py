from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ExploreQuickFinishReq, ExploreQuickFinishRsp, PackNotice, StatusCode
import utils.garden_state as garden_state
import utils.db as db
from utils import item_mgr
from handlers.Explore import (
    activity_config,
    load_activity_state,
    load_area_state,
    save_activity_state,
    save_area_state,
    validate_duration,
    validate_quick_cost,
)


@packet_handler(MsgId.ExploreQuickFinishReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreQuickFinishReq()
        req.ParseFromString(data)
        rsp = ExploreQuickFinishRsp(is_activity=req.is_activity)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            if req.is_activity:
                self._finish_activity(session, req, rsp, pack)
            else:
                self._finish_area(session, req, rsp, pack)
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del pack.items[:]
        session.send(MsgId.ExploreQuickFinishRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)

    @staticmethod
    def _finish_activity(session, req, rsp, pack):
        cfg = activity_config(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            return
        validate_duration(cfg)
        cost_item, cost_count = validate_quick_cost(cfg)
        key = str(cfg["i_d"])
        with (
            item_mgr.player_lock(session.player_id),
            item_mgr.deferred_notifications(),
            db.transaction(),
        ):
            state = load_activity_state(session.player_id, key)
            if not state["start_time"]:
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_EXISTS
                return
            info = rsp.explore
            info.explore_id = req.explore_id
            info.times = int(state.get("times", 0))
            info.start_time = int(state["start_time"])
            info.is_quick_finish = bool(state.get("is_quick_finish"))
            if not info.is_quick_finish:
                if not item_mgr.consume_items(
                    session.player_id,
                    [(cost_item, cost_count)],
                    pack_notice=pack,
                    session=session,
                ):
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    return
                state["is_quick_finish"] = True
                save_activity_state(session.player_id, key, state)
                info.is_quick_finish = True
            rsp.status = StatusCode.StatusCode_OK

    @staticmethod
    def _finish_area(session, req, rsp, pack):
        cfg = garden_state.explore_area_cfg(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            return
        validate_duration(cfg)
        cost_item, cost_count = validate_quick_cost(cfg)
        with (
            item_mgr.player_lock(session.player_id),
            item_mgr.deferred_notifications(),
            db.transaction(),
        ):
            state = load_area_state(session.player_id, req.explore_id)
            if not state["start_time"]:
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_EXISTS
                garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
                return
            if not state.get("is_quick_finish"):
                if not item_mgr.consume_items(
                    session.player_id,
                    [(cost_item, cost_count)],
                    pack_notice=pack,
                    session=session,
                ):
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
                    return
                state["is_quick_finish"] = True
                save_area_state(session.player_id, req.explore_id, state)
            rsp.status = StatusCode.StatusCode_OK
            garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
