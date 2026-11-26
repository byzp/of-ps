from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ActivityRegularRewardReq, ActivityRegularRewardRsp, PackNotice, StatusCode
from server import activities


@packet_handler(MsgId.ActivityRegularRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityRegularRewardReq()
        req.ParseFromString(data)
        rsp = ActivityRegularRewardRsp(param=req.param, pool_type=req.pool_type)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        rsp.status = activities.claim_regular_reward(
            session.player_id, req.activity_id, req.pool_type, req.param, rsp.rewards, pack
        )
        session.send(MsgId.ActivityRegularRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
            activities.report_rewards(session, rsp.rewards)
