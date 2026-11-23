from config import Config
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    DailyTaskExchangeReq,
    DailyTaskExchangeRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils import refresh


@packet_handler(MsgId.DailyTaskExchangeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DailyTaskExchangeReq()
        req.ParseFromString(data)

        rsp = DailyTaskExchangeRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 兑换档位查 DailyTask.daily_task_reward: {i_d(当日第N次), step,
        _steps = res.get("DailyTask", {}).get("daily_task_reward", {}).get("datas")
        steps = (
            sorted(_steps, key=lambda e: e.get("i_d", 0))
            if isinstance(_steps, (list, tuple))
            else ()
        )
        if not steps:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)
            return

        # 当日已兑换次数持久化(kv ns=daily, 按天 key 自然过期)
        day = str(refresh.day_index())
        count_key = f"exchange:{day}"
        used = int(db.get_kv(session.player_id, "daily", count_key, 0) or 0)
        if used >= len(steps):
            rsp.status = StatusCode.StatusCode_DAILY_WISH_TIMES_NOT_ENOUGH
            rsp.today_converted = used
            session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)
            return

        # 逐档兑换: 第 N 次消耗 daily_task_reward[i_d=N].cost_item_num;
        # exchange_all=True 时连续兑换到碎片不足或次数用尽
        cost_item_id = steps[0].get("cost_item_i_d", 124)
        frag_num = item_mgr.get_num(session.player_id, cost_item_id)
        gained = 0
        total_cost = 0
        for idx in range(used, len(steps)):
            cost = steps[idx].get("cost_item_num", 0)
            if frag_num < cost:
                break
            frag_num -= cost
            total_cost += cost
            gained += 1
            if not req.exchange_all:
                break
        if gained == 0:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            rsp.today_converted = used
            session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)
            return

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        # 扣祈愿碎片(整体校验后统一扣, 并发下不足则整单失败)
        if not item_mgr.consume_items(
            session.player_id,
            [(cost_item_id, total_cost)],
            pack_notice=rsp1,
            session=session,
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            rsp.today_converted = used
            session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)
            return

        converted = db.incr_kv(session.player_id, "daily", count_key, gained)

        # 发放祈愿石(每次兑换 1 个)
        item_mgr.grant_items(
            session.player_id,
            [(Config.WISH_STONE_ITEM_ID, gained)],
            rsp_items=rsp.rewards,
            pack_notice=rsp1,
            session=session,
        )

        rsp.today_converted = converted

        session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)  # 每日兑换 2602 2603
        session.send(MsgId.PackNotice, rsp1, 0)
