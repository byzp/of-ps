from utils import achieve_track as _at

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ChallengeStateUpdateReq,
    ChallengeStateUpdateRsp,
    StatusCode,
    BattleState,
)

import utils.db as db
from utils.res_loader import res
from utils import item_mgr


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
            star = 0
            asset = ""
            challenge_scene = None
            for i in res["Challenge"]["challenge"]["datas"]:
                if i["i_d"] == req.challenge_id:
                    asset = i.get("asset_full_name", "")
                    challenge_scene = i.get("scene_i_d")
                    star_rewards = {3: 1000, 2: 600, 1: 300}
                    if rsp.challenge_data.use_time <= i["star_timer3"]:
                        rsp.challenge_data.star = 3
                    elif rsp.challenge_data.use_time <= i["star_timer2"]:
                        rsp.challenge_data.star = 2
                    elif rsp.challenge_data.use_time <= i["star_timer1"]:
                        rsp.challenge_data.star = 1
                    star = rsp.challenge_data.star
                    break
            if star:
                item_mgr.grant_items(
                    session.player_id,
                    [(101, star_rewards[star])],
                    session=session,
                )
            # 成就: 完成竞速挑战101(TimeSpeed/TimeStar/TimeRun 竞速族) /
            # 完成世界挑战102(其余玩法), 按当前世界/场景计数

            racing = any(k in asset for k in ("TimeSpeed", "TimeStar", "TimeRun"))
            _at.report(
                session,
                "race_done" if racing else "world_challenge_done",
                match=challenge_scene,
            )
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
