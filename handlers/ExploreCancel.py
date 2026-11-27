from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ExploreCancelReq, ExploreCancelRsp, StatusCode
import utils.garden_state as garden_state
import utils.db as db
from utils import item_mgr
from handlers.Explore import (
    activity_config,
    load_activity_state,
    load_area_state,
    save_activity_state,
    save_area_state,
)


@packet_handler(MsgId.ExploreCancelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreCancelReq()
        req.ParseFromString(data)
        rsp = ExploreCancelRsp(
            status=StatusCode.StatusCode_OK,
            explore_id=req.explore_id,
            is_activity=req.is_activity,
        )
        try:
            if req.is_activity:
                self._cancel_activity(session, req, rsp)
            else:
                self._cancel_area(session, req, rsp)
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
        session.send(MsgId.ExploreCancelRsp, rsp, packet_id)

    @staticmethod
    def _cancel_activity(session, req, rsp):
        cfg = activity_config(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            return
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
            state["start_time"] = 0
            state["is_quick_finish"] = False
            state["collectable"] = False
            # 次数是开始时的预留; 取消必须归还, 否则一次取消会永久消耗挑战次数。
            state["times"] = item_mgr.validate_counter(
                state["times"] - 1, label="explore times"
            )
            save_activity_state(session.player_id, key, state)
            info = rsp.explore
            info.explore_id = req.explore_id
            info.times = item_mgr.validate_counter(
                int(state.get("times", 0)), label="explore times"
            )
            info.start_time = 0

    @staticmethod
    def _cancel_area(session, req, rsp):
        if garden_state.explore_area_cfg(req.explore_id) is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            return
        with (
            item_mgr.player_lock(session.player_id),
            item_mgr.deferred_notifications(),
            db.transaction(),
        ):
            state = load_area_state(session.player_id, req.explore_id)
            if not state["start_time"]:
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_EXISTS
            else:
                state["start_time"] = 0
                state["is_quick_finish"] = False
                save_area_state(session.player_id, req.explore_id, state)
                rsp.status = StatusCode.StatusCode_OK
            garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
