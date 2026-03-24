from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    ChallengeStateUpdateReq,
    ChallengeStateUpdateRsp,
    StatusCode,
    BattleState,
)

import utils.db as db
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChallengeStateUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChallengeStateUpdateReq()
        req.ParseFromString(data)

        rsp = ChallengeStateUpdateRsp()
        rsp.status = StatusCode.StatusCode_OK
        if req.battle_state == BattleState.Finish:
            challenge_b = db.get_challenge(
                session.player_id, session.scene_id, req.challenge_id
            )
            if challenge_b:
                rsp.challenge_data.ParseFromString(challenge_b)
                if req.use_time < rsp.challenge_data.use_time:
                    rsp.challenge_data.use_time = req.use_time
            else:
                rsp.challenge_data.challenge_id = req.challenge_id
                rsp.challenge_data.use_time = req.use_time
            rsp.challenge_data.state = BattleState.Finish
            for i in res["Challenge"]["challenge"]["datas"]:
                if i["i_d"] == req.challenge_id:
                    if rsp.challenge_data.use_time <= i["star_timer_3"]:  # TODO 奖励
                        rsp.challenge_data.star = 3
                    elif rsp.challenge_data.use_time <= i["star_timer_2"]:
                        rsp.challenge_data.star = 2
                    elif rsp.challenge_data.use_time <= i["star_timer_1"]:
                        rsp.challenge_data.star = 1
            db.set_challenge(
                session.player_id,
                session.scene_id,
                req.challenge_id,
                rsp.challenge_data.SerializeToString(),
            )
        else:
            rsp.challenge_data.challenge_id = req.challenge_id
            rsp.challenge_data.state = req.battle_state

        session.send(MsgId.ChallengeStateUpdateRsp, rsp, packet_id)
