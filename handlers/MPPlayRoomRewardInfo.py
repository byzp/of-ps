from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import MPPlayRoomRewardInfoReq, MPPlayRoomRewardInfoRsp, StatusCode
from server import mp_room_rewards


@packet_handler(MsgId.MPPlayRoomRewardInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        MPPlayRoomRewardInfoReq().ParseFromString(data)
        rsp = MPPlayRoomRewardInfoRsp(status=StatusCode.StatusCode_OK)
        for kind in ('score', 'extra_bonus', 'extra_mag'):
            setattr(rsp, f'{kind}_day_remain', mp_room_rewards.remaining(session.player_id, kind, 'day'))
            setattr(rsp, f'{kind}_week_remain', mp_room_rewards.remaining(session.player_id, kind, 'week'))
        session.send(MsgId.MPPlayRoomRewardInfoRsp, rsp, packet_id)
