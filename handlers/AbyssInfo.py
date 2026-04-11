from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time
from datetime import datetime

from proto.net_pb2 import AbyssInfoRsp, StatusCode, DungeonData

import utils.db as db
from utils.res_loader import res
from utils.algo import char_unpack

logger = logging.getLogger(__name__)


@packet_handler(MsgId.AbyssInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = AbyssInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        dungeons = db.get_dungeon(session.player_id)
        seasons = [(9000001, 1000)]  # 常规深渊
        for i in res["Abyss"]["abyss_season"]["datas"]:
            if (
                i.get("end_time")
                and time.time()
                < datetime.strptime(i["end_time"], "%Y-%m-%d %H:%M:%S").timestamp()
            ):
                rsp.in_progress_season_id = i["i_d"]
                seasons.append((i["i_d"], i["season_stage"]))  # 周期性深渊
                break
        for i in seasons:
            for ii in res["Abyss"]["abyss_stage"]["datas"]:
                if ii["i_d"] == i[1]:
                    for iii in ii["abyss_stage_group_info"]:
                        if dungeons.get(iii["dungeon_i_d"]):
                            di = rsp.abyss_info.season_info[i[0]].dungeon_info[
                                iii["dungeon_i_d"]
                            ]
                            tmp = DungeonData()
                            tmp.ParseFromString(dungeons[iii["dungeon_i_d"]])
                            di.dungeon_id = tmp.dungeon_id
                            team = di.abyss_teams.add()
                            team.char1 = char_unpack(tmp.char1)[0]
                            team.char2 = char_unpack(tmp.char2)[0]
                            team.char3 = char_unpack(tmp.char3)[0]
                            if iii.get("is_double_team"):
                                team = di.abyss_teams.add()
                                team.char1 = char_unpack(tmp.char1)[1]
                                team.char2 = char_unpack(tmp.char2)[1]
                                team.char3 = char_unpack(tmp.char3)[1]
                            di.finish_time = tmp.last_finish_time
        session.send(MsgId.AbyssInfoRsp, rsp, packet_id)
