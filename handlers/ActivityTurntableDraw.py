from config import Config
import random
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityTurntableDrawReq,
    ActivityTurntableDrawRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res
from utils.activity_state import template_id

"""
# 活动转盘抽奖 2635 2636
配置来源 ActivityTurntable.json:
- activity_turntable(i_d=活动 id): turntable_pool_i_d 奖池, cost_item_i_d 抽奖消耗道具,
  first_one_need_item_num 首抽消耗数量 / one_need_item_num 每抽消耗数量
  (首抽 6 后续 1, 语义按字段名推断)
- turntable_pool.turntable_pool_item: {index 格子号, item_i_d, item_num,
  limit_num 该格可抽次数, weight 权重, is_special}
抽奖记录持久化到 turntable_record 表, 兼作各格 limit_num 的已抽计数
"""


def _turntable_cfg(activity_id):
    for row in res["ActivityTurntable"]["activity_turntable"]["datas"]:
        if row.get("i_d") == template_id(activity_id):
            return row
    return None


def _pool_items(pool_id):
    for row in res["ActivityTurntable"]["turntable_pool"]["datas"]:
        if row.get("i_d") == pool_id:
            return row.get("turntable_pool_item", ())
    return ()


@packet_handler(MsgId.ActivityTurntableDrawReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityTurntableDrawReq()
        req.ParseFromString(data)

        rsp = ActivityTurntableDrawRsp()
        rsp.activity_id = req.activity_id

        cfg = _turntable_cfg(req.activity_id)
        items = _pool_items(cfg.get("turntable_pool_i_d")) if cfg else ()
        if not items:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ActivityTurntableDrawRsp, rsp, packet_id)  # 2635,2636
            return

        draw_times = min(max(req.draw_times, 1), Config.TURNTABLE_MAX_DRAW_TIMES)
        cost_item = cfg.get("cost_item_i_d", 0)
        first_num = cfg.get("first_one_need_item_num", 0)
        one_num = cfg.get("one_need_item_num", 0)

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK

        # 各格已抽次数(以持久化抽奖记录计, 校验 limit_num)
        used = db.get_turntable_used_counts(session.player_id, req.activity_id)
        is_first = not db.has_turntable_drawn(session.player_id, req.activity_id)

        # 按剩余可抽格子规划本次抽取
        plan = []
        for _ in range(draw_times):
            avail = [
                it
                for it in items
                if used.get(it.get("index", 0), 0) < it.get("limit_num", 0)
                or not it.get("limit_num", 0)  # limit_num 缺省视为不限
            ]
            if not avail:
                break
            weights = [it.get("weight", 0) for it in avail]
            if sum(weights) > 0:
                hit = random.choices(avail, weights=weights)[0]
            else:
                hit = random.choice(avail)
            used[hit.get("index", 0)] = used.get(hit.get("index", 0), 0) + 1
            plan.append(hit)

        if not plan:
            rsp.status = StatusCode.StatusCode_TURNTABLE_NO_REWARD_REMAIN
            session.send(MsgId.ActivityTurntableDrawRsp, rsp, packet_id)  # 2635,2636
            return

        # 抽奖消耗: 首抽 first_one_need_item_num, 之后每抽 one_need_item_num
        cost = (first_num if is_first else one_num) + (len(plan) - 1) * one_num
        if cost_item and not db.consume_item(session.player_id, cost_item, cost, pack):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.ActivityTurntableDrawRsp, rsp, packet_id)  # 2635,2636
            return

        # 写入持久化抽奖记录, 供 ActivityTurntableRecord 查询及 limit_num 计数
        now = int(time.time())
        for it in plan:
            db.add_turntable_record(
                session.player_id,
                req.activity_id,
                it.get("index", 0),
                it.get("item_i_d", 0),
                it.get("item_num", 0),
                now,
            )

        rsp.status = StatusCode.StatusCode_OK
        rewards = []
        for it in plan:
            rsp.reward_indexes.append(it.get("index", 0))
            if it.get("item_i_d") and it.get("item_num", 0) > 0:
                rewards.append((it["item_i_d"], it["item_num"]))
        db.grant_rewards(session.player_id, rewards, rsp.rewards, pack)

        session.send(MsgId.ActivityTurntableDrawRsp, rsp, packet_id)  # 2635,2636
        session.send(MsgId.PackNotice, pack, 0)
