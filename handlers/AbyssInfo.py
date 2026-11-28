import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import AbyssInfoRsp, DungeonData, StatusCode
from server import abyss
import utils.db as db


@packet_handler(MsgId.AbyssInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = AbyssInfoRsp(status=StatusCode.StatusCode_OK)
        dungeons = db.get_dungeon(session.player_id)
        if not isinstance(dungeons, dict):
            dungeons = {}
        now = int(time.time())
        active = abyss.current_season(now)
        if active:
            rsp.in_progress_season_id = active["i_d"]
        for season_data in abyss.visible_seasons(now):
            season_info = rsp.abyss_info.season_info[season_data["i_d"]]
            season_info.season_id = season_data["i_d"]
            for entry in abyss.stage_rows(season_data):
                dungeon_id = int(entry["dungeon_i_d"])
                info = season_info.dungeon_info[dungeon_id]
                info.dungeon_id = dungeon_id
                blob = dungeons.get(dungeon_id)
                if not blob:
                    continue
                data_info = DungeonData()
                data_info.ParseFromString(blob)
                for members in abyss.stored_teams(data_info):
                    if not any(members):
                        continue
                    team = info.abyss_teams.add()
                    team.char1, team.char2, team.char3 = members
                info.finish_time = data_info.last_finish_time
        session.send(MsgId.AbyssInfoRsp, rsp, packet_id)
