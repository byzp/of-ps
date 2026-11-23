from config import Config
import pickle as _pk

import time as _t

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ExploreRewardReq, ExploreRewardRsp, PackNotice, StatusCode
import utils.garden_state as garden_state
import utils.db as db
from utils.res_loader import res
from utils import item_mgr
from utils import achieve_track

"""
# 领取探索派遣奖励 1825 1826
产出物取 Explore.json explore_area.explore_area_item, 完成校验用 need_time(秒)
"""


@packet_handler(MsgId.ExploreRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreRewardReq()
        req.ParseFromString(data)

        rsp = ExploreRewardRsp()
        rsp.is_activity = req.is_activity
        rsp.explore_id = req.explore_id

        # 活动探索领奖(Explore.explore_activity): need_time 到期后领取
        if req.is_activity:

            _act = next(
                (
                    row
                    for row in res["Explore"]["explore_activity"]["datas"]
                    if isinstance(row, dict) and row.get("i_d") == req.explore_id
                ),
                None,
            )
            if not _act:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.ExploreRewardRsp, rsp, packet_id)
                return
            key = str(_act["i_d"])
            raw = db.get_kv(session.player_id, "activity_explore", key, b"")
            st = _pk.loads(raw) if raw else {}
            start = int(st.get("start_time", 0))
            if not start:
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_FINISH
                session.send(MsgId.ExploreRewardRsp, rsp, packet_id)
                return
            if not st.get("is_quick_finish") and _t.time() < start + int(
                _act.get("need_time", 0)
            ):
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_FINISH
                info = rsp.explore
                info.explore_id = _act["i_d"]
                info.times = int(st.get("times", 0))
                info.start_time = start
                session.send(MsgId.ExploreRewardRsp, rsp, packet_id)
                return

            pack = PackNotice()
            pack.status = StatusCode.StatusCode_OK
            grants = []
            sid = int(_act.get("special_reward_item_i_d", 0))
            if sid:
                grants.append((sid, 1))
            for it in _act.get("explore_activity_item", ()) or ():
                iid = int(it.get("rewar_item_i_d", 0))
                if iid:
                    grants.append((iid, 1))
            item_mgr.grant_items(
                session.player_id,
                [g for g in grants if g[0]],
                session=session,
                pack_notice=pack,
                rsp_items=rsp.reward_item,
            )
            st.pop("start_time", None)
            st["is_quick_finish"] = False
            st["collectable"] = False
            db.set_kv(session.player_id, "activity_explore", key, _pk.dumps(st))
            rsp.status = StatusCode.StatusCode_OK
            info = rsp.explore
            info.explore_id = _act["i_d"]
            info.times = int(st.get("times", 0))
            info.collect_reward = True
            session.send(MsgId.ExploreRewardRsp, rsp, packet_id)  # 1825,1826
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
            return

        e = garden_state.get_explore(session.player_id, req.explore_id)
        if not e["start_time"]:
            # 未派遣, 无奖励可领
            rsp.status = StatusCode.StatusCode_EXPLORE_NOT_FINISH
            garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
            session.send(MsgId.ExploreRewardRsp, rsp, packet_id)  # 1825,1826
            return

        # 完成校验: 到达 need_time(explore_area.need_time, 秒)或已快速完成
        cfg = garden_state.explore_area_cfg(req.explore_id)
        need_ms = (cfg.get("need_time", 0) if cfg else 0) * 1000
        if (
            not e["is_quick_finish"]
            and need_ms
            and garden_state.now_ms() < e["start_time"] + need_ms
        ):
            rsp.status = StatusCode.StatusCode_EXPLORE_NOT_FINISH
            garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
            session.send(MsgId.ExploreRewardRsp, rsp, packet_id)  # 1825,1826
            return

        rsp.status = StatusCode.StatusCode_OK
        e["times"] += 1
        e["start_time"] = 0
        e["is_quick_finish"] = False
        garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
        garden_state.set_explore(session.player_id, req.explore_id, e)

        # 发放产出物(explore_area.explore_area_item.rewar_item_i_d)
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        for item_id in garden_state.explore_collect_items(req.explore_id):
            gain, total = garden_state.grant_stack_item(
                session.player_id, item_id, Config.EXPLORE_REWARD_COUNT_PER_ITEM
            )
            rsp.reward_item.add().CopyFrom(gain)
            pack.items.add().CopyFrom(total)

        # 委托/探索奖励领取计数(仅普通探索，活动探索不是委托奖励)。
        achieve_track.report(session, "explore_reward")

        session.send(MsgId.ExploreRewardRsp, rsp, packet_id)  # 1825,1826
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)  # 背包变化通知
