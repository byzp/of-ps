from utils import achieve_track, battle_rewards

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    BattleState,
    BattleEncounterStateUpdateReq,
    BattleEncounterStateUpdateRsp,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res

"""
# 战斗遭遇状态更新 1327 1328
状态持久化于 db player_kv ns=encounter k=states,
与 BattleEncounterInfo 共用同一处读写。
"""


@packet_handler(MsgId.BattleEncounterStateUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BattleEncounterStateUpdateReq()
        req.ParseFromString(data)

        # 持久化遭遇战状态, 保证两接口状态一致
        previous = db.get_encounter_states(session.player_id)
        state = (
            BattleState.Close
            if req.battle_state == BattleState.Fail
            else req.battle_state
        )
        db.set_encounter_state(session.player_id, req.encounter_id, state)

        rsp = BattleEncounterStateUpdateRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.encounter.battle_id = req.encounter_id
        if req.battle_state == BattleState.Fail:
            rsp.encounter.state = BattleState.Close
        else:
            rsp.encounter.state = req.battle_state
        rsp.encounter.box_id = 0

        # 成就: 完成遭遇战103(按世界/场景) / 遭遇战获胜5(区域)

        if (
            req.battle_state == BattleState.Finish
            and previous.get(req.encounter_id, (0, 0))[0] != BattleState.Finish
        ):
            battle_rewards.grant_character_exp(session, "encounter", req.encounter_id)
        session.send(MsgId.BattleEncounterStateUpdateRsp, rsp, packet_id)
        if req.battle_state == BattleState.Finish:
            # 成就: 完成遭遇战(按世界/场景计数 + 获胜 + 指定坐标清除灰物,
            # 事件层归族; 主线任务条件由 achieve_track->quest_track 推进)
            achieve_track.report(
                session,
                "encounter_done",
                match=req.encounter_id,
                scene=getattr(session, "scene_id", 0),
            )
