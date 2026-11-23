from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AbyssAllServerRankReq,
    AbyssAllServerRankRsp,
    StatusCode,
)

import utils.db as db
from utils.rank_service import abyss_season_summary
from utils.pb_create import make_PlayerBriefInfo

"""
# 深渊全服榜 2661 2662
全部玩家按该赛季总用时升序(仅统计有通关记录者), 前 50 名;
entry.total_time = 赛季各副本最佳用时之和。
"""


@packet_handler(MsgId.AbyssAllServerRankReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbyssAllServerRankReq()
        req.ParseFromString(data)

        rsp = AbyssAllServerRankRsp()
        rsp.status = StatusCode.StatusCode_OK

        board = []
        for pid in db.get_player_ids():
            finished, total_time = abyss_season_summary(pid, req.season_id)
            if finished > 0 and total_time > 0:
                board.append((total_time, finished, pid))
        board.sort(key=lambda e: (e[0], -e[1], e[2]))
        for total_time, _finished, pid in board[: Config.MAX_RANK_ENTRIES]:
            info = rsp.rank_list.add()
            info.season_id = req.season_id
            info.total_time = total_time
            make_PlayerBriefInfo(pid, info.player_info)

        session.send(MsgId.AbyssAllServerRankRsp, rsp, packet_id)  # 2661,2662
