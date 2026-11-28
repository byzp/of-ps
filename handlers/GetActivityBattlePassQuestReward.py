from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import GetActivityBattlePassQuestRewardReq, GetActivityBattlePassQuestRewardRsp
from server import activities


@packet_handler(MsgId.GetActivityBattlePassQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetActivityBattlePassQuestRewardReq()
        req.ParseFromString(data)
        rsp = GetActivityBattlePassQuestRewardRsp()
        rsp.status, (rsp.add_exp, rsp.current_lv, rsp.current_week_exp, rsp.current_total_exp, rsp.current_exp) = activities.claim_battle_pass_quest(
            session.player_id, req.activity_battle_pass_id, req.achieve_id
        )
        session.send(MsgId.GetActivityBattlePassQuestRewardRsp, rsp, packet_id)
