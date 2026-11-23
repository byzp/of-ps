from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityRegularRewardReq,
    ActivityRegularRewardRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res
from utils import achieve_track, item_mgr, refresh
from utils.activity_state import template_id

"""
# 常规活动领奖 1995 1996
配置来源 ActivityRegular.json:
- activity_regular(i_d=活动 id)有四类奖池字段: daily_pool_i_d / random_pool_i_d /
  pool_i_d / daily_refresh_pool_i_d(池 id 后缀 1/2/3 对应 daily/random/pool),
  按 req.pool_type 1/2/3 选择, 缺失时退化为该活动任一存在的池
- activity_regular_pool.activity_regular_pool_item:
  {achieve_i_d, days, activity_regular_pool_reward_item[{item_i_d, item_num}]},
  req.param 匹配 achieve_i_d
"""


def _regular_pool(activity_id, pool_type):
    """按活动 id + pool_type 选择奖池行; 找不到返回 None"""
    regs = res["ActivityRegular"]["activity_regular"]["datas"]
    pools = res["ActivityRegular"]["activity_regular_pool"]["datas"]
    reg = None
    for row in regs:
        if row.get("i_d") == template_id(activity_id):
            reg = row
            break
    if reg is None:
        return None
    # pool_type: 1=每日 2=随机 3=累计(依据池 id 后缀 1/2/3 推断)
    by_type = {
        1: reg.get("daily_pool_i_d") or reg.get("daily_refresh_pool_i_d"),
        2: reg.get("random_pool_i_d"),
        3: reg.get("pool_i_d"),
    }
    pool_id = by_type.get(pool_type)
    if not pool_id:  # 该类型无池时退化为该活动任一存在的池
        pool_id = next((v for v in by_type.values() if v), None)
    if not pool_id:
        return None
    for row in pools:
        if row.get("i_d") == pool_id:
            return row
    return None


@packet_handler(MsgId.ActivityRegularRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityRegularRewardReq()
        req.ParseFromString(data)

        rsp = ActivityRegularRewardRsp()
        rsp.param = req.param
        rsp.pool_type = req.pool_type

        pool = _regular_pool(req.activity_id, req.pool_type)
        rewards = None
        if pool is not None:
            for it in pool.get("activity_regular_pool_item", ()):
                if it.get("achieve_i_d") == req.param:
                    rewards = [
                        (r["item_i_d"], r.get("item_num", 0))
                        for r in it.get("activity_regular_pool_reward_item", ())
                        if r.get("item_i_d") and r.get("item_num", 0) > 0
                    ]
                    break

        if rewards is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ActivityRegularRewardRsp, rsp, packet_id)  # 1995,1996
            return

        rsp.status = StatusCode.StatusCode_OK
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        period = f":d{refresh.day_index()}" if req.pool_type == 1 else ""
        if not db.try_claim(
            session.player_id,
            "activity_regular",
            f"{req.activity_id}:{req.pool_type}:{req.param}{period}",
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.ActivityRegularRewardRsp, rsp, packet_id)  # 1995,1996
            return
        with achieve_track.batch(session):
            item_mgr.grant_items(
                session.player_id,
                rewards,
                rsp_items=rsp.rewards,
                pack_notice=pack,
                session=session,
            )
            session.send(MsgId.ActivityRegularRewardRsp, rsp, packet_id)
            session.send(MsgId.PackNotice, pack, 0)
