import pickle as _pk

import time as _t

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ExploreReq, ExploreRsp, ItemDetail, StatusCode
import utils.db as db
from utils.res_loader import res
import utils.garden_state as garden_state

"""
# 开始探索派遣 1821 1822
配置来源 Explore.json explore_area:
need_player_level 等级门槛, need_item/need_item_count 准入道具, need_time 时长(秒)
"""


@packet_handler(MsgId.ExploreReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreReq()
        req.ParseFromString(data)

        rsp = ExploreRsp()
        rsp.is_activity = req.is_activity

        # 活动探索(Explore.explore_activity): is_activity=True 时走独立状态机
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
                session.send(MsgId.ExploreRsp, rsp, packet_id)
                return

            key = str(_act["i_d"])
            raw = db.get_kv(session.player_id, "activity_explore", key, b"")
            st = _pk.loads(raw) if raw else {}
            times = int(st.get("times", 0))
            if st.get("start_time"):
                rsp.status = StatusCode.StatusCode_EXPLORE_IN_PROGRESS
                rsp.explore.explore_id = req.explore_id
                rsp.explore.times = times
                rsp.explore.start_time = int(st["start_time"])
                rsp.explore.is_quick_finish = bool(st.get("is_quick_finish"))
                session.send(MsgId.ExploreRsp, rsp, packet_id)
                return
            if int(_act.get("max_times", 0)) and times >= int(_act.get("max_times", 0)):
                rsp.status = StatusCode.StatusCode_EXPLORE_NUM_LIMIT
                session.send(MsgId.ExploreRsp, rsp, packet_id)
                return
            st["start_time"] = int(_t.time())
            st["is_quick_finish"] = False
            st["times"] = times + 1
            # 达到 need_time 后可领奖(collectable 由 ExploreReward 判定)
            st["collectable"] = False
            db.set_kv(
                session.player_id,
                "activity_explore",
                key,
                _pk.dumps(st),
            )
            rsp.status = StatusCode.StatusCode_OK
            info = rsp.explore
            info.explore_id = _act["i_d"]
            info.times = st["times"]
            info.start_time = st["start_time"]
            session.send(MsgId.ExploreRsp, rsp, packet_id)
            return

        cfg = garden_state.explore_area_cfg(req.explore_id)
        if cfg is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ExploreRsp, rsp, packet_id)  # 1821,1822
            return

        # 等级门槛(explore_area.need_player_level)
        need_level = cfg.get("need_player_level", 0)
        if need_level:
            row = db.get_players_info(session.player_id, "level")
            level = row[0] if row else 0
            if level < need_level:
                rsp.status = StatusCode.StatusCode_PLAYER_LEVEL_LIMIT
                session.send(MsgId.ExploreRsp, rsp, packet_id)  # 1821,1822
                return

        # 准入道具(explore_area.need_item/need_item_count): 仅校验持有量;
        # 表中另有 quick_need_item 专字段作消耗, 该字段是否每次派遣扣除未知, 故不扣
        need_item = cfg.get("need_item", 0)
        need_count = cfg.get("need_item_count", 0)
        if need_item and need_count:
            raw = db.get_item_detail(session.player_id, need_item)
            have = 0
            if raw:
                detail = ItemDetail()
                detail.ParseFromString(raw)
                have = detail.main_item.base_item.num
            if have < need_count:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.ExploreRsp, rsp, packet_id)  # 1821,1822
                return

        e = garden_state.get_explore(session.player_id, req.explore_id)
        if e["start_time"]:
            # 已经在派遣中
            rsp.status = StatusCode.StatusCode_EXPLORE_IN_PROGRESS
        else:
            rsp.status = StatusCode.StatusCode_OK
            e["start_time"] = garden_state.now_ms()
            e["is_quick_finish"] = False

        garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
        garden_state.set_explore(session.player_id, req.explore_id, e)

        session.send(MsgId.ExploreRsp, rsp, packet_id)  # 1821,1822
