from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ChallengeFriendRankReq,
    ChallengeFriendRankRsp,
    StatusCode,
    ChallengeData,
)

import utils.db as db
from utils.pb_create import make_PlayerBriefInfo


@packet_handler(MsgId.ChallengeFriendRankReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChallengeFriendRankReq()
        req.ParseFromString(data)

        rsp = ChallengeFriendRankRsp()
        rsp.status = StatusCode.StatusCode_OK

        c = rsp.self_challenge
        c.player_id = session.player_id
        c_data = ChallengeData()
        for i in db.get_challenge(session.player_id, session.scene_id):
            c_data.ParseFromString(i)
            tmp = c.challenge_infos.add()
            tmp.challenge_id = c_data.challenge_id
            tmp.use_time = c_data.use_time

        for friend_info in db.get_friend_info(
            session.player_id,
            None,
            "friend_id,friend_status",
        ):
            if friend_info[1] == 2:
                info = rsp.rank_info.add()
                make_PlayerBriefInfo(friend_info[0], info.player_info)
                c = info.challenge
                c.player_id = friend_info[0]
                c_data = ChallengeData()
                for i in db.get_challenge(friend_info[0], session.scene_id):
                    c_data.ParseFromString(i)
                    tmp = c.challenge_infos.add()
                    tmp.challenge_id = c_data.challenge_id
                    tmp.use_time = c_data.use_time

        session.send(MsgId.ChallengeFriendRankRsp, rsp, packet_id)
