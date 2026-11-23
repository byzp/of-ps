from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    IntervalJoinReq,
    IntervalJoinRsp,
    IntervalChangeNotice,
    StatusCode,
)
import utils.garden_state as garden_state
import utils.db as db
from server.scene_data import get_session

"""
# 加入好友的间隙帮忙加速 1835 1836 -> 1832
配置来源 Explore.json explore_interval:
- retention_time(秒): 间隙保留时长, 超过后不可再加入(INTERVAL_OVERDUE)
- member_count: 参与人数上限
- 每人帮忙缩短 time/member_count 秒: 表中无单次加速字段,
  按"满员恰好加速完整个 time"推算(机制为推测, 数值来自表)
"""


@packet_handler(MsgId.IntervalJoinReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = IntervalJoinReq()
        req.ParseFromString(data)

        rsp = IntervalJoinRsp()
        rsp.friend_id = str(req.friend_id)

        # 好友间隙可能未在内存态(如重启后), 容错创建
        info = garden_state.get_interval(req.friend_id, create=True)
        cfg = garden_state.interval_cfg(info["interval_id"])
        rsp.explore_id = info["interval_id"]
        rsp.finish_time = info["finish_time"]

        now = garden_state.now_ms()
        if info["finish_time"] <= now:
            # 已完成的间隙不能再帮忙
            rsp.status = StatusCode.StatusCode_INTERVAL_FINISH
            session.send(MsgId.IntervalJoinRsp, rsp, packet_id)  # 1835,1836
            return

        # 保留期校验(explore_interval.retention_time, 秒)
        retention_ms = (cfg.get("retention_time", 0) if cfg else 0) * 1000
        if retention_ms and now > info["create_time"] + retention_ms:
            rsp.status = StatusCode.StatusCode_INTERVAL_OVERDUE
            session.send(MsgId.IntervalJoinRsp, rsp, packet_id)  # 1835,1836
            return

        if any(m["player_id"] == session.player_id for m in info["member"]):
            # 已参与过: 幂等返回当前状态, 不重复加速
            rsp.status = StatusCode.StatusCode_OK
            session.send(MsgId.IntervalJoinRsp, rsp, packet_id)  # 1835,1836
            return

        # 人数上限(explore_interval.member_count)
        member_limit = cfg.get("member_count", 0) if cfg else 0
        if member_limit and len(info["member"]) >= member_limit:
            rsp.status = StatusCode.StatusCode_FAIL  # 无专用"间隙人数已满"状态码
            session.send(MsgId.IntervalJoinRsp, rsp, packet_id)  # 1835,1836
            return

        # 加速: 每人缩短 time/member_count 秒(见文件头注释)
        if cfg and cfg.get("time") and cfg.get("member_count"):
            speed_up_ms = cfg["time"] * 1000 // cfg["member_count"]
        else:
            speed_up_ms = Config.INTERVAL_SPEED_UP_MS_FALLBACK
        info["finish_time"] = max(now, info["finish_time"] - speed_up_ms)

        info["member"].append(
            {
                "player_id": session.player_id,
                "nick_name": session.player_name,
                "head": session.avatar_id,
                "join_time": now,
                "is_reward": False,
            }
        )

        rsp.status = StatusCode.StatusCode_OK
        rsp.finish_time = info["finish_time"]
        garden_state.set_interval(req.friend_id, info)

        session.send(MsgId.IntervalJoinRsp, rsp, packet_id)  # 1835,1836

        # 通知在线的间隙主人: 完成时间发生变化
        for s in get_session():
            if s.player_id == req.friend_id:
                notice = IntervalChangeNotice()
                notice.status = StatusCode.StatusCode_OK
                notice.player_id = req.friend_id
                notice.interval_id = info["interval_id"]
                notice.finish_time = info["finish_time"]
                s.send(MsgId.IntervalChangeNotice, notice, 0)  # 1832
                break
