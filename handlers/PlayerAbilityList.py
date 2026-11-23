from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import PlayerAbilityListRsp, StatusCode

import utils.db as db


@packet_handler(MsgId.PlayerAbilityListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):

        rsp = PlayerAbilityListRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 能力等级与 PlayerAbilityLevelUp 同源: kv ns=ability, k=ability_id, v=level
        levels = db.get_kv_ns(session.player_id, "ability")
        for k, v in levels.items():
            if not isinstance(k, (int, str)) or not isinstance(v, (int, str)):
                continue
            ability_id, level = int(k), int(v)
            ability = rsp.ability_list.add()
            ability.ability_id = ability_id
            ability.level = level

        session.send(MsgId.PlayerAbilityListRsp, rsp, packet_id)  # 1611,1612
