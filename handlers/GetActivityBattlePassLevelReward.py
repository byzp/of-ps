from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import GetActivityBattlePassLevelRewardReq, GetActivityBattlePassLevelRewardRsp, PackNotice, StatusCode
from server import activities


@packet_handler(MsgId.GetActivityBattlePassLevelRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetActivityBattlePassLevelRewardReq()
        req.ParseFromString(data)
        rsp = GetActivityBattlePassLevelRewardRsp()
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        rsp.status = activities.claim_battle_pass_level_reward(
            session.player_id,
            req.activity_battle_pass_id,
            req.level,
            req.is_get_free_reward,
            rsp.rewards,
            pack,
        )
        session.send(MsgId.GetActivityBattlePassLevelRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
