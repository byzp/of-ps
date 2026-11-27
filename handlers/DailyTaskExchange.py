from config import Config

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
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            rows = res.get("DailyTask", {}).get("daily_task_reward", {}).get("datas")
            steps = sorted(rows, key=lambda e: e.get("i_d", 0)) if isinstance(rows, (list, tuple)) else ()
            if not steps:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            else:
                day = str(refresh.day_index())
                with item_mgr.player_lock(session.player_id), item_mgr.deferred_notifications(), db.transaction():
                    count_key = f"exchange:{day}"
                    used = item_mgr.validate_counter(
                        int(db.get_kv(session.player_id, "daily", count_key, 0) or 0),
                        label="daily exchange count",
                    )
                    rsp.today_converted = used
                    if used >= len(steps):
                        rsp.status = StatusCode.StatusCode_DAILY_WISH_TIMES_NOT_ENOUGH
                    else:
                        cost_item_id = steps[0].get("cost_item_i_d", 124)
                        item_mgr.validate_stackable_item_id(cost_item_id)
                        item_mgr.validate_stackable_item_id(Config.WISH_STONE_ITEM_ID)
                        frag_num = item_mgr.get_num(session.player_id, cost_item_id)
                        gained = 0
                        total_cost = 0
                        claimed_indexes = []
                        for idx in range(used, len(steps)):
                            cost = item_mgr.validate_count(
                                steps[idx].get("cost_item_num", 0),
                                allow_zero=True,
                                label="daily exchange cost",
                            )
                            if frag_num < cost:
                                break
                            frag_num -= cost
                            total_cost = item_mgr.checked_add(total_cost, cost)
                            gained = item_mgr.checked_add(gained, 1)
                            claimed_indexes.append(idx)
                            if not req.exchange_all:
                                break
                        if not gained:
                            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                        else:
                            # 整批奖励先验证, 再写逐档 claim; 后续失败由事务整体回滚。
                            item_mgr.validate_rewards(
                                [(Config.WISH_STONE_ITEM_ID, gained)]
                            )
                            for idx in claimed_indexes:
                                if not db.try_claim(
                                    session.player_id,
                                    "daily_task_exchange",
                                    f"{day}:{idx}",
                                ):
                                    raise item_mgr.EconomyConfigError(
                                        "daily exchange slot already claimed"
                                    )
                            if not item_mgr.consume_items(
                                session.player_id,
                                [(cost_item_id, total_cost)],
                                pack_notice=notice,
                                session=session,
                            ):
                                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                            else:
                                item_mgr.grant_items(
                                    session.player_id,
                                    [(Config.WISH_STONE_ITEM_ID, gained)],
                                    rsp_items=rsp.rewards,
                                    pack_notice=notice,
                                    session=session,
                                )
                                converted = item_mgr.checked_add(
                                    used, gained, limit=Config.ECONOMY_UINT32_MAX
                                )
                                db.set_kv(
                                    session.player_id, "daily", count_key, converted
                                )
                                rsp.today_converted = converted
                                rsp.status = StatusCode.StatusCode_OK
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.rewards[:]
            del notice.items[:]

        session.send(MsgId.DailyTaskExchangeRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and notice.items:
            session.send(MsgId.PackNotice, notice, 0)
