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
        tmp = DungeonData()
        tmp.ParseFromString(db.get_dungeon(session.player_id, session.dungeon[0]))
        char_ids = []
        char_ids.append(char_unpack(tmp.char1)[1])
        char_ids.append(char_unpack(tmp.char2)[1])
        char_ids.append(char_unpack(tmp.char3)[1])
        rsp.team.CopyFrom(make_SceneTeam(session.player_id, char_ids))
        session.send(MsgId.AbyssTeamSwitchRsp, rsp, packet_id)
