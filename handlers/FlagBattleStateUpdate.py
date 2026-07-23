from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config

from proto.net_pb2 import (
    FlagBattleStateUpdateReq,
    FlagBattleStateUpdateRsp,
    StatusCode,
    BattleState,
)

from utils.pb_create import make_Achieve
from utils.pb_create import make_QuestNotice


@packet_handler(MsgId.FlagBattleStateUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FlagBattleStateUpdateReq()
        req.ParseFromString(data)

        rsp = FlagBattleStateUpdateRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.battle_data.battle_id = req.battle_id
        rsp.battle_data.state = req.battle_state
        rsp.battle_data.type = req.mission_type
        if req.battle_state == BattleState.Finish:
            make_Achieve(session, req.battle_id)
        if not Config.SKIP_QUESTS and req.battle_id == 1002:
            rsp1 = make_QuestNotice(session, [11000741])
            if rsp1:
                session.send(MsgId.QuestNotice, rsp1, 0)

        session.send(MsgId.FlagBattleStateUpdateRsp, rsp, packet_id)
