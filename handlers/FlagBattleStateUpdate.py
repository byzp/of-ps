from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    FlagBattleStateUpdateReq,
    FlagBattleStateUpdateRsp,
    StatusCode,
    BattleState,
)

from utils.pb_create import make_Achieve


@packet_handler(MsgId.FlagBattleStateUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FlagBattleStateUpdateReq()
        req.ParseFromString(data)

        rsp = FlagBattleStateUpdateRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.battle_data.battle_id = req.battle_id
        rsp.battle_data.state = req.battle_state
        if req.battle_state == BattleState.Finish:
            make_Achieve(session, req.battle_id)

        session.send(MsgId.FlagBattleStateUpdateRsp, rsp, packet_id)
