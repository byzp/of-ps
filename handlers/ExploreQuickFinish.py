import pickle as _pk

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ExploreQuickFinishReq,
    ExploreQuickFinishRsp,
    PackNotice,
    StatusCode,
)
import utils.garden_state as garden_state
import utils.db as db
from utils import item_mgr
from utils.res_loader import res

"""
# 探索派遣快速完成 1823 1824
消耗 Explore.json explore_area.quick_need_item × quick_need_item_count(全表均为 102×1)
"""


@packet_handler(MsgId.ExploreQuickFinishReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreQuickFinishReq()
        req.ParseFromString(data)

        rsp = ExploreQuickFinishRsp()
        rsp.is_activity = req.is_activity

        # 活动探索快结(Explore.explore_activity): 扣 quick_need_item 立即可领奖
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
                session.send(MsgId.ExploreQuickFinishRsp, rsp, packet_id)
                return

            key = str(_act["i_d"])
            raw = db.get_kv(session.player_id, "activity_explore", key, b"")
            st = _pk.loads(raw) if raw else {}
            if not st.get("start_time"):
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_EXISTS
                session.send(MsgId.ExploreQuickFinishRsp, rsp, packet_id)
                return
            info = rsp.explore
            info.explore_id = _act["i_d"]
            info.times = int(st.get("times", 0))
            info.start_time = int(st["start_time"])
            info.is_quick_finish = bool(st.get("is_quick_finish"))
            pack = PackNotice()
            pack.status = StatusCode.StatusCode_OK
            if not info.is_quick_finish:
                cost_id = int(_act.get("quick_need_item", 0))
                cost_num = int(_act.get("quick_need_item_count", 0))
                if (
                    cost_id
                    and cost_num
                    and not item_mgr.consume_items(
                        session.player_id,
                        [(cost_id, cost_num)],
                        pack_notice=pack,
                        session=session,
                    )
                ):
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    session.send(MsgId.ExploreQuickFinishRsp, rsp, packet_id)
                    return
                st["is_quick_finish"] = True
                db.set_kv(session.player_id, "activity_explore", key, _pk.dumps(st))
                info.is_quick_finish = True
            rsp.status = StatusCode.StatusCode_OK
            session.send(MsgId.ExploreQuickFinishRsp, rsp, packet_id)
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
            return

        cfg = garden_state.explore_area_cfg(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ExploreQuickFinishRsp, rsp, packet_id)  # 1823,1824
            return

        e = garden_state.get_explore(session.player_id, req.explore_id)
        if not e["start_time"]:
            # 未在派遣中, 无法快速完成
            rsp.status = StatusCode.StatusCode_EXPLORE_NOT_EXISTS
            garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
            session.send(MsgId.ExploreQuickFinishRsp, rsp, packet_id)  # 1823,1824
            return

        pack = None
        if not e["is_quick_finish"]:
            # 扣快速完成消耗(explore_area.quick_need_item/quick_need_item_count)
            cost_item = cfg.get("quick_need_item", 0)
            cost_num = cfg.get("quick_need_item_count", 0)
            if cost_item and cost_num:
                total = garden_state.consume_stack_item(
                    session.player_id, cost_item, cost_num
                )
                if total is None:
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
                    session.send(
                        MsgId.ExploreQuickFinishRsp, rsp, packet_id
                    )  # 1823,1824
                    return
                pack = PackNotice()
                pack.status = StatusCode.StatusCode_OK
                pack.items.add().CopyFrom(total)
            e["is_quick_finish"] = True

        rsp.status = StatusCode.StatusCode_OK
        garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
        garden_state.set_explore(session.player_id, req.explore_id, e)

        session.send(MsgId.ExploreQuickFinishRsp, rsp, packet_id)  # 1823,1824
        if pack is not None:
            session.send(MsgId.PackNotice, pack, 0)  # 背包变化通知
