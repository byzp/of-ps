from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    AbyssTeamUpdateReq,
    AbyssTeamUpdateRsp,
    StatusCode,
    DungeonData,
)

import utils.db as db
from utils.algo import char_unpack, char_pack

logger = logging.getLogger(__name__)


@packet_handler(MsgId.AbyssTeamUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbyssTeamUpdateReq()
        req.ParseFromString(data)

        rsp = AbyssTeamUpdateRsp()
        rsp.status = StatusCode.StatusCode_OK
        dg_b = db.get_dungeon(session.player_id, req.dungeon_id)
        dg = DungeonData()
        if dg_b:
            dg.ParseFromString(dg_b)
        else:
            dg.dungeon_id = req.dungeon_id

        if req.team_index == 0:
            dg.char1 = char_pack(req.abyss_team.char1, char_unpack(dg.char1)[1])
            dg.char2 = char_pack(req.abyss_team.char2, char_unpack(dg.char2)[1])
            dg.char3 = char_pack(req.abyss_team.char3, char_unpack(dg.char3)[1])
        if req.team_index == 1:
            dg.char1 = char_pack(char_unpack(dg.char1)[0], req.abyss_team.char1)
            dg.char2 = char_pack(char_unpack(dg.char2)[0], req.abyss_team.char2)
            dg.char3 = char_pack(char_unpack(dg.char3)[0], req.abyss_team.char3)
        db.set_dungeon(session.player_id, dg.dungeon_id, dg.SerializeToString())
        session.send(MsgId.AbyssTeamUpdateRsp, rsp, packet_id)
