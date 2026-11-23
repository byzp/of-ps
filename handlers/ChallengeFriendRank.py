from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ChallengeFriendRankReq,
    ChallengeFriendRankRsp,
    StatusCode,
    ChallengeData,
)

import utils.db as db
from utils.rank_service import friend_ids, challenge_best_times, sort_by_time_asc
from utils.pb_create import make_PlayerBriefInfo

"""
# 挑战好友榜 1301 1302
当前场景各挑战的最优用时(ChallengeData.use_time, 按挑战id取最小);
榜内按最优用时升序, 无成绩靠后。
"""


@packet_handler(MsgId.ChallengeFriendRankReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChallengeFriendRankReq()
        req.ParseFromString(data)

        rsp = ChallengeFriendRankRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 自己的成绩缓存
        c = rsp.self_challenge
        c.player_id = session.player_id
        best = challenge_best_times(session.player_id, session.scene_id)
        for cid, t in sorted(best.items()):
            tmp = c.challenge_infos.add()
            tmp.challenge_id = cid
            tmp.use_time = t

        board = []
        for pid in friend_ids(session.player_id):
            times = (
                best
                if pid == session.player_id
                else challenge_best_times(pid, session.scene_id)
            )
            total = sum(times.values())
            board.append((pid, total))
        for pid in sort_by_time_asc(board):
            info = rsp.rank_info.add()
            make_PlayerBriefInfo(pid, info.player_info)
            cc = info.challenge
            cc.player_id = pid
            times = (
                best
                if pid == session.player_id
                else challenge_best_times(pid, session.scene_id)
            )
            for cid, t in sorted(times.items()):
                tmp = cc.challenge_infos.add()
                tmp.challenge_id = cid
                tmp.use_time = t

        session.send(MsgId.ChallengeFriendRankRsp, rsp, packet_id)
