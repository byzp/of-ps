from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ActivityGiftRewardReq, ActivityGiftRewardRsp, PackNotice, StatusCode
from server import activities


@packet_handler(MsgId.ActivityGiftRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityGiftRewardReq()
        req.ParseFromString(data)
        rsp = ActivityGiftRewardRsp()
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        rsp.status = activities.claim_gift_reward(
            session.player_id, req.activity_id, req.achieve_id, rsp.rewards, pack
        )
        session.send(MsgId.ActivityGiftRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
