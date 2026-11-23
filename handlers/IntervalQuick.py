from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import IntervalQuickReq, IntervalQuickRsp, PackNotice, StatusCode
import utils.garden_state as garden_state
import utils.db as db

"""
# 快速完成自己的间隙 1837 1838
消耗 Explore.json explore_interval.quick_need_item × quick_need_item_count(全表均为 102×10)
"""


@packet_handler(MsgId.IntervalQuickReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = IntervalQuickReq()
        req.ParseFromString(data)

        rsp = IntervalQuickRsp()

        info = garden_state.get_interval(session.player_id)
        if info is None:
            rsp.status = StatusCode.StatusCode_INTERVAL_NOT_EXISTS
            session.send(MsgId.IntervalQuickRsp, rsp, packet_id)  # 1837,1838
            return

        rsp.explore_id = info["interval_id"]
        rsp.finish_time = info["finish_time"]

        if info["finish_time"] <= garden_state.now_ms():
            # 已经完成, 无需(也不能)再快速完成
            rsp.status = StatusCode.StatusCode_INTERVAL_FINISH
            session.send(MsgId.IntervalQuickRsp, rsp, packet_id)  # 1837,1838
            return

        # 扣快速完成消耗(explore_interval.quick_need_item/quick_need_item_count)
        pack = None
        cfg = garden_state.interval_cfg(info["interval_id"])
        cost_item = cfg.get("quick_need_item", 0) if cfg else 0
        cost_num = cfg.get("quick_need_item_count", 0) if cfg else 0
        if cost_item and cost_num:
            total = garden_state.consume_stack_item(
                session.player_id, cost_item, cost_num
            )
            if total is None:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.IntervalQuickRsp, rsp, packet_id)  # 1837,1838
                return
            pack = PackNotice()
            pack.status = StatusCode.StatusCode_OK
            pack.items.add().CopyFrom(total)

        rsp.status = StatusCode.StatusCode_OK
        info["finish_time"] = garden_state.now_ms()
        rsp.finish_time = info["finish_time"]
        garden_state.set_interval(session.player_id, info)

        session.send(MsgId.IntervalQuickRsp, rsp, packet_id)  # 1837,1838
        if pack is not None:
            session.send(MsgId.PackNotice, pack, 0)  # 背包变化通知
