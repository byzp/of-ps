import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import AbyssTeamSwitchReq, AbyssTeamSwitchRsp, StatusCode
from server import abyss
from utils.pb_create import make_SceneTeam


@packet_handler(MsgId.AbyssTeamSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbyssTeamSwitchReq()
        req.ParseFromString(data)
        rsp = AbyssTeamSwitchRsp()
        current = getattr(session, "dungeon", None)
        dungeon_id = int(current[0]) if current else 0
        now = int(time.time())
        season_data = next(
            (item for item in abyss.visible_seasons(now) if abyss.stage_entry(item, dungeon_id)), None
        )
        entry, config, error = abyss.validate_team(
            session.player_id, season_data, dungeon_id, 1, [0, 0, 0]
        )
        # validate_team 的成员检查针对写入请求；切换仅要求当前为双队副本。
        if error and not (entry and config and error == StatusCode.StatusCode_DungeonTeamFull):
            rsp.status = error or StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.AbyssTeamSwitchRsp, rsp, packet_id)
            return
        dg = abyss.load_dungeon(session.player_id, dungeon_id)
        members = abyss.stored_teams(dg)[1] if dg else [0, 0, 0]
        _, _, team_error = abyss.validate_team(session.player_id, season_data, dungeon_id, 1, members)
        if team_error:
            rsp.status = team_error
        else:
            make_SceneTeam(session.player_id, members, rsp.team, dungeon_id=dungeon_id)
            rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.AbyssTeamSwitchRsp, rsp, packet_id)
