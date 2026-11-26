import pickle as _pk
import time as _t

from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ExploreRewardReq, ExploreRewardRsp, PackNotice, StatusCode
import utils.garden_state as garden_state
import utils.db as db
from utils import achieve_track, item_mgr
from handlers.Explore import (
    activity_config,
    activity_rewards,
    area_rewards,
    validate_duration,
)


@packet_handler(MsgId.ExploreRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreRewardReq()
        req.ParseFromString(data)
        rsp = ExploreRewardRsp(is_activity=req.is_activity, explore_id=req.explore_id)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            if req.is_activity:
                self._claim_activity(session, req, rsp, pack)
            else:
                self._claim_area(session, req, rsp, pack)
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.reward_item[:]
            del pack.items[:]
        session.send(MsgId.ExploreRewardRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        if not req.is_activity:
            achieve_track.report(session, "explore_reward")
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)

    @staticmethod
    def _claim_activity(session, req, rsp, pack):
        cfg = activity_config(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            return
        duration = validate_duration(cfg)
        rewards = activity_rewards(cfg)
        key = str(cfg["i_d"])
        with item_mgr.player_lock(session.player_id), db.transaction():
            raw = db.get_kv(session.player_id, "activity_explore", key, b"")
            state = _pk.loads(raw) if raw else {}
            start = int(state.get("start_time", 0) or 0)
            if not start:
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_FINISH
                return
            if not state.get("is_quick_finish") and _t.time() < start + duration:
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_FINISH
                info = rsp.explore
                info.explore_id = req.explore_id
                info.times = int(state.get("times", 0))
                info.start_time = start
                return
            item_mgr.grant_items(
                session.player_id,
                rewards,
                rsp_items=rsp.reward_item,
                pack_notice=pack,
                session=session,
            )
            state.pop("start_time", None)
            state["is_quick_finish"] = False
            state["collectable"] = False
            db.set_kv(session.player_id, "activity_explore", key, _pk.dumps(state))
            rsp.status = StatusCode.StatusCode_OK
            info = rsp.explore
            info.explore_id = req.explore_id
            info.times = int(state.get("times", 0))
            info.collect_reward = True

    @staticmethod
    def _claim_area(session, req, rsp, pack):
        cfg = garden_state.explore_area_cfg(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            return
        duration = validate_duration(cfg)
        item_mgr.validate_count(
            Config.EXPLORE_REWARD_COUNT_PER_ITEM, label="explore reward count"
        )
        rewards = [
            (item_id, item_mgr.checked_mul(Config.EXPLORE_REWARD_COUNT_PER_ITEM, 1))
            for item_id, _ in area_rewards(req.explore_id)
        ]
        with item_mgr.player_lock(session.player_id), db.transaction():
            state = garden_state.get_explore(session.player_id, req.explore_id)
            start = int(state.get("start_time", 0) or 0)
            if not start:
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_FINISH
                garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
                return
            if not state.get("is_quick_finish") and garden_state.now_ms() < start + duration * 1000:
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_FINISH
                garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
                return
            item_mgr.grant_items(
                session.player_id,
                rewards,
                rsp_items=rsp.reward_item,
                pack_notice=pack,
                session=session,
            )
            state["times"] = item_mgr.checked_add(
                item_mgr.validate_counter(state.get("times", 0), label="explore times"),
                1,
                limit=Config.ECONOMY_UINT32_MAX,
            )
            state["start_time"] = 0
            state["is_quick_finish"] = False
            garden_state.set_explore(session.player_id, req.explore_id, state)
            rsp.status = StatusCode.StatusCode_OK
            garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
