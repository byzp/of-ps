from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ActivitySignInReq, ActivitySignInRsp, PackNotice, StatusCode
from server import activities


@packet_handler(MsgId.ActivitySignInReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivitySignInReq()
        req.ParseFromString(data)
        rsp = ActivitySignInRsp(day=req.day)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        rsp.status, rsp.reward_id = activities.claim_sign_in(
            session.player_id, req.activity_id, req.day, rsp.rewards, pack
        )
        session.send(MsgId.ActivitySignInRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
            activities.report_rewards(session, rsp.rewards)
