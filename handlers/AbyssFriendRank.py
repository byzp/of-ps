from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import AbyssFriendRankReq, AbyssFriendRankRsp, StatusCode

from server import abyss
import utils.db as db
from utils.rank_service import friend_ids, abyss_season_summary, fill_abyss_season_info
from utils.pb_create import make_PlayerBriefInfo

"""
# 深渊好友榜 2119 2120
榜内=自己+双向好友, 按赛季通关副本数降序 -> 总用时升序。
"""


@packet_handler(MsgId.AbyssFriendRankReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbyssFriendRankReq()
        req.ParseFromString(data)

        rsp = AbyssFriendRankRsp()
        if abyss.season(req.season_id) is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.AbyssFriendRankRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK

        entries = []
        for pid in [session.player_id] + friend_ids(session.player_id):
            finished, total_time = abyss_season_summary(pid, req.season_id)
            entries.append((finished, total_time, pid))
        # 通关数降序, 用时升序
        entries.sort(key=lambda e: (-e[0], e[1], e[2]))
        for finished, total_time, pid in entries:
            info = rsp.rank_list.add()
            make_PlayerBriefInfo(pid, info.player_info)
            fill_abyss_season_info(pid, req.season_id, info.abyss_info)

        session.send(MsgId.AbyssFriendRankRsp, rsp, packet_id)  # 2119,2120
