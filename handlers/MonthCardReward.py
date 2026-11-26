from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import MonthCardRewardReq, MonthCardRewardRsp, PackNotice, StatusCode
from server import activities


@packet_handler(MsgId.MonthCardRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        MonthCardRewardReq().ParseFromString(data)
        rsp = MonthCardRewardRsp()
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        gains = []
        rsp.status, rsp.month_card_reward_days = activities.claim_month_card(
            session.player_id, gains, pack
        )
        session.send(MsgId.MonthCardRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
            activities.report_rewards(session, gains)
