from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import IntervalStartReq, IntervalStartRsp, StatusCode
import utils.garden_state as garden_state
import utils.db as db

"""
# 开启自己的好友间隙 1833 1834
"""


@packet_handler(MsgId.IntervalStartReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = IntervalStartReq()
        req.ParseFromString(data)

        rsp = IntervalStartRsp()
        rsp.status = StatusCode.StatusCode_OK

        info = garden_state.get_interval(session.player_id)
        if info is None or info["finish_time"] <= garden_state.now_ms():
            # 不存在或上一轮已结束, 开启新一轮
            garden_state.reset_interval(session.player_id)
            info = garden_state.get_interval(session.player_id, create=True)

        rsp.explore_id = info["interval_id"]
        rsp.finish_time = info["finish_time"]

        session.send(MsgId.IntervalStartRsp, rsp, packet_id)  # 1833,1834
