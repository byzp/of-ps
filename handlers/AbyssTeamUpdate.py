from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import AbyssTeamUpdateReq, AbyssTeamUpdateRsp, DungeonData, StatusCode
from server import abyss
import utils.db as db


@packet_handler(MsgId.AbyssTeamUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbyssTeamUpdateReq()
        req.ParseFromString(data)
        rsp = AbyssTeamUpdateRsp()
        # 请求只携带 dungeon_id；赛季由包含该副本的可见赛季决定，避免依赖客户端回传。
        season_data = next(
            (
                season
                for season in abyss.visible_seasons()
                if abyss.stage_entry(season, req.dungeon_id) is not None
            ),
            None,
        )
        if season_data is None:
            season_data = abyss.current_season()
        members = abyss.team_members(req.abyss_team)
        with abyss.lock, db.transaction():
            entry, config, error = abyss.validate_team(
                session.player_id, season_data, req.dungeon_id, req.team_index, members
            )
            if error:
                rsp.status = error
            else:
                dg = abyss.load_dungeon(session.player_id, req.dungeon_id)
                if dg is None:
                    dg = DungeonData(dungeon_id=req.dungeon_id)
                abyss.set_team(dg, req.team_index, members)
                db.set_dungeon(session.player_id, req.dungeon_id, dg.SerializeToString())
                rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.AbyssTeamUpdateRsp, rsp, packet_id)
