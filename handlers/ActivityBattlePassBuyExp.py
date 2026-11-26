from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ActivityBattlePassBuyExpReq, ActivityBattlePassBuyExpRsp, PackNotice, StatusCode
from server import activities


@packet_handler(MsgId.ActivityBattlePassBuyExpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityBattlePassBuyExpReq()
        req.ParseFromString(data)
        rsp = ActivityBattlePassBuyExpRsp(activity_battle_pass_id=req.activity_battle_pass_id)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        rsp.status, (rsp.battle_pass_lv, rsp.total_exp, rsp.current_exp) = activities.buy_battle_pass_exp(
            session.player_id, req.activity_battle_pass_id, packet_id, rsp, pack
        )
        session.send(MsgId.ActivityBattlePassBuyExpRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
