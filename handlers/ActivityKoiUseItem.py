import random

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityKoiUseItemReq,
    ActivityKoiUseItemRsp,
    ItemDetail,
    StatusCode,
    PackNotice,
)
import utils.db as db
import pickle
from utils.res_loader import res

"""
# 锦鲤活动使用道具(获得抽奖码) 4519 4520
配置来源 ActivityJinli.json jinli(i_d=活动 id, 表内为 260326180):
- params2: 消耗道具 id(6044), 每个换一组抽奖码
- params3: 每个道具产出的抽奖码数量(1)
- params1: 单人抽奖码数量上限(20, 语义按数值推断)
- params4=30 / settle_time 为开奖参数, 本 handler 不使用
"""


def _koi_cfg(activity_id):
    """取锦鲤配置; 活动 id 不匹配时容错取表内第一条"""
    if not (
        "ActivityJinli" in res
        and "jinli" in res["ActivityJinli"]
        and "datas" in res["ActivityJinli"]["jinli"]
    ):
        return None
    rows = res["ActivityJinli"]["jinli"]["datas"]
    for row in rows:
        if row.get("i_d") == activity_id:
            return row
    if rows:
        return rows[0]
    return None


@packet_handler(MsgId.ActivityKoiUseItemReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityKoiUseItemReq()
        req.ParseFromString(data)

        rsp = ActivityKoiUseItemRsp()
        rsp.num = req.num
        rsp.activity_id = req.activity_id

        cfg = _koi_cfg(req.activity_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ActivityKoiUseItemRsp, rsp, packet_id)  # 4519,4520
            return

        code_limit = cfg.get("params1", 0) or 20
        cost_item = cfg.get("params2", 0)
        codes_per_item = cfg.get("params3", 0) or 1
        use_num = min(max(req.num, 1), code_limit)

        # 扣消耗道具(jinli.params2 × 使用个数)
        pack = None
        if cost_item:
            pack = PackNotice()
            pack.status = StatusCode.StatusCode_OK
            if not db.consume_item(session.player_id, cost_item, use_num, pack):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.ActivityKoiUseItemRsp, rsp, packet_id)  # 4519,4520
                return

        rsp.status = StatusCode.StatusCode_OK
        rsp.num = use_num
        # 抽奖码持久化于 kv(ns=koi_codes), "单人上限"按历史累计校验
        raw = db.get_kv(session.player_id, "koi_codes", str(req.activity_id), b"")
        codes = pickle.loads(raw) if raw else []
        if len(codes) + use_num * codes_per_item > code_limit:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.ActivityKoiUseItemRsp, rsp, packet_id)  # 4519,4520
            return
        for _ in range(use_num * codes_per_item):
            code = "%08d" % random.randint(0, 99999999)
            codes.append(code)
            rsp.codes.append(code)
        db.set_kv(
            session.player_id,
            "koi_codes",
            str(req.activity_id),
            pickle.dumps(codes),
        )

        session.send(MsgId.ActivityKoiUseItemRsp, rsp, packet_id)  # 4519,4520
        if pack is not None:
            session.send(MsgId.PackNotice, pack, 0)  # 背包变化通知
