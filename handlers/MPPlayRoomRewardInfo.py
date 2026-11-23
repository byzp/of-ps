from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPPlayRoomRewardInfoReq,
    MPPlayRoomRewardInfoRsp,
    StatusCode,
)


@packet_handler(MsgId.MPPlayRoomRewardInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPPlayRoomRewardInfoReq()
        req.ParseFromString(data)

        rsp = MPPlayRoomRewardInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.score_day_remain = 10
        rsp.score_week_remain = 70
        rsp.extra_bonus_day_remain = 10
        rsp.extra_bonus_week_remain = 70
        rsp.extra_mag_day_remain = 10
        rsp.extra_mag_week_remain = 70

        session.send(
            MsgId.MPPlayRoomRewardInfoRsp, rsp, packet_id
        )  # 2515,2516 房间奖励次数查询
