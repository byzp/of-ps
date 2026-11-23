from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BossRushFriendRankReq,
    BossRushFriendRankRsp,
    BossRushInfo,
    StatusCode,
)

from utils import db
from utils.rank_service import friend_ids, boss_rush_best_score
from utils.pb_create import make_PlayerBriefInfo
from utils.res_loader import res


def _season_exists(season_id: int) -> bool:
    for s in res["BossRush"]["boss_rush_season"]["datas"]:
        if s["i_d"] == season_id:
            return True
    return False


@packet_handler(MsgId.BossRushFriendRankReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushFriendRankReq()
        req.ParseFromString(data)

        rsp = BossRushFriendRankRsp()
        rsp.season_id = req.season_id
        if not _season_exists(req.season_id):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.BossRushFriendRankRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK

        board = []
        for pid in [session.player_id] + friend_ids(session.player_id):
            score = boss_rush_best_score(pid, req.season_id)
            if score > 0:
                board.append((score, pid))
        board.sort(key=lambda e: (-e[0], e[1]))
        total = len(board)
        for pos, (score, pid) in enumerate(board):
            info = rsp.rank_info.add()
            make_PlayerBriefInfo(pid, info.player_info)
            ri = info.rank_info
            ri.player_id = pid
            ri.score = score
            if total > 1:
                ri.rank_ratio = pos * 10000 // total
            else:
                blob = db.get_boss_rush_info(pid, req.season_id)
                if blob:
                    br = BossRushInfo()
                    br.ParseFromString(blob)
                    ri.rank_ratio = br.total_rank_ratio

        session.send(MsgId.BossRushFriendRankRsp, rsp, packet_id)  # 2711,2712
