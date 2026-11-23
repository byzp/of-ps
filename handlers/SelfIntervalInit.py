from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import SelfIntervalInitReq, SelfIntervalInitRsp, StatusCode
import utils.garden_state as garden_state
import utils.db as db

"""
# 自身间隙初始化 1843 1844
间隙状态统一走 utils/garden_state 内存态,
与 IntervalStart/IntervalQuick/IntervalJoin 的读写口径保持一致
"""


@packet_handler(MsgId.SelfIntervalInitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SelfIntervalInitReq()
        req.ParseFromString(data)

        rsp = SelfIntervalInitRsp()
        rsp.status = StatusCode.StatusCode_OK

        info = garden_state.get_interval(session.player_id)
        if info is not None and info["finish_time"] > garden_state.now_ms():
            # 有进行中的间隙
            rsp.is_start = True
            rsp.interval_id = info["interval_id"]
            rsp.end_time = info["finish_time"]

            interval = rsp.interval
            interval.interval_id = info["interval_id"]
            interval.finish_time = info["finish_time"]
            interval.player_id = session.player_id
            interval.create_time = info["create_time"]
            for m in info["member"]:
                member = interval.member.add()
                member.player_id = m["player_id"]
                member.nick_name = m["nick_name"]
                member.head = m["head"]
                member.join_time = m["join_time"]
                member.is_reward = m["is_reward"]
        else:
            # 未开启(或上一轮已结束, 等待 IntervalStart 开新一轮)
            rsp.is_start = False

        session.send(MsgId.SelfIntervalInitRsp, rsp, packet_id)  # 1843,1844
