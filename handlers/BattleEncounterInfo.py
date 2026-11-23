from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import BattleEncounterInfoReq, BattleEncounterInfoRsp, StatusCode

import utils.db as db

"""
# 战斗遭遇信息 1329 1330
遭遇战状态持久化于 db player_kv ns=encounter k=states,
与 BattleEncounterStateUpdate 共用同一处读写, 服务器重启不丢失。
"""


@packet_handler(MsgId.BattleEncounterInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BattleEncounterInfoReq()
        req.ParseFromString(data)

        rsp = BattleEncounterInfoRsp()
        rsp.status = StatusCode.StatusCode_OK

        player_states = db.get_encounter_states(session.player_id)

        # 按请求的 encounter_ids 返回已记录的状态, 无记录时返回默认值(Start/无宝箱)
        for encounter_id in req.encounter_ids:
            encounter = rsp.encounters.add()
            encounter.battle_id = encounter_id
            state, box_id = player_states.get(encounter_id, (0, 0))
            encounter.state = state
            encounter.box_id = box_id

        session.send(MsgId.BattleEncounterInfoRsp, rsp, packet_id)  # 1329,1330
