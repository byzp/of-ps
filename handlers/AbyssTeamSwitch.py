from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AbyssTeamSwitchReq,
    AbyssTeamSwitchRsp,
    StatusCode,
    StatusCode,
    DungeonData,
)

from utils.pb_create import make_SceneTeam
from utils.algo import char_unpack
import utils.db as db


@packet_handler(MsgId.AbyssTeamSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbyssTeamSwitchReq()
        req.ParseFromString(data)

        rsp = AbyssTeamSwitchRsp()
        rsp.status = StatusCode.StatusCode_OK
        dg_b = db.get_dungeon(session.player_id, session.dungeon[0])
        if not dg_b or isinstance(dg_b, dict):
            session.send(MsgId.AbyssTeamSwitchRsp, rsp, packet_id)
            return
        tmp = DungeonData()
        tmp.ParseFromString(dg_b)
        char_ids = []
        char_ids.append(char_unpack(tmp.char1)[1])
        char_ids.append(char_unpack(tmp.char2)[1])
        char_ids.append(char_unpack(tmp.char3)[1])
        make_SceneTeam(
            session.player_id, char_ids, rsp.team, dungeon_id=session.dungeon[0]
        )
        session.send(MsgId.AbyssTeamSwitchRsp, rsp, packet_id)
