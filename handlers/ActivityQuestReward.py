from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ActivityQuestRewardReq, ActivityQuestRewardRsp, PackNotice, StatusCode
from server import activities


@packet_handler(MsgId.ActivityQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityQuestRewardReq()
        req.ParseFromString(data)
        rsp = ActivityQuestRewardRsp(param=req.param, is_progress=req.is_progress)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        rsp.status, _ = activities.claim_activity_quest(
            session.player_id,
            req.activity_id,
            req.param,
            req.is_progress,
            rsp.rewards,
            pack,
        )
        session.send(MsgId.ActivityQuestRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
            activities.report_rewards(session, rsp.rewards)
