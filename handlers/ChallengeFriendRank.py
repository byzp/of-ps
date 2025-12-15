from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as ChallengeFriendRankReq_pb2
import proto.OverField_pb2 as ChallengeFriendRankRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


# 挑战好友排行信息列表
# 1301 1302
@packet_handler(MsgId.ChallengeFriendRankReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChallengeFriendRankReq_pb2.ChallengeFriendRankReq()
        req.ParseFromString(data)

        rsp = ChallengeFriendRankRsp_pb2.ChallengeFriendRankRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Hardcoded test data
        # Set status
        rsp.status = TEST_DATA["status"]

        # Add rank info
        for rank_data in TEST_DATA["rank_info"]:
            rank_info = rsp.rank_info.add()

            # Player info
            player_info = rank_info.player_info
            player_data = rank_data["player_info"]
            for key, value in player_data.items():
                setattr(player_info, key, value)

            # Challenge info
            challenge = rank_info.challenge
            challenge_data = rank_data["challenge"]
            challenge.player_id = challenge_data["player_id"]

            for challenge_info_data in challenge_data["challenge_infos"]:
                challenge_info = challenge.challenge_infos.add()
                challenge_info.challenge_id = challenge_info_data["challenge_id"]
                challenge_info.use_time = challenge_info_data["use_time"]

        # Self challenge
        self_challenge = rsp.self_challenge
        self_challenge_data = TEST_DATA["self_challenge"]
        self_challenge.player_id = self_challenge_data["player_id"]

        for challenge_info_data in self_challenge_data["challenge_infos"]:
            challenge_info = self_challenge.challenge_infos.add()
            challenge_info.challenge_id = challenge_info_data["challenge_id"]
            challenge_info.use_time = challenge_info_data["use_time"]

        session.send(MsgId.ChallengeFriendRankRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "rank_info": [
        {
            "player_info": {
                "player_id": 1111111,
                "nick_name": "测试123",
                "level": 50,
                "head": 9345,
                "last_login_time": 0,
                "team_leader_badge": 5047,
                "sex": 0,
                "phone_background": 8031,
                "is_online": False,
                "sign": "测试123",
                "guild_name": "",
                "character_id": 202004,
                "create_time": 1743502390,
                "player_label": 2401700,
                "garden_like_num": 379,
                "account_type": 30114,
                "birthday": "1992-09-14",
                "hide_value": 0,
                "avatar_frame": 7222,
            },
            "challenge": {
                "player_id": 1111111,
                "challenge_infos": [
                    {"challenge_id": 400003, "use_time": 12521},
                    {"challenge_id": 1052002, "use_time": 40222},
                ],
            },
        },
        {
            "player_info": {
                "player_id": 2921793,
                "nick_name": "测试234",
                "level": 45,
                "head": 9345,
                "last_login_time": 0,
                "team_leader_badge": 5048,
                "sex": 0,
                "phone_background": 8032,
                "is_online": True,
                "sign": "测试234",
                "guild_name": "",
                "character_id": 202004,
                "create_time": 1743502390,
                "player_label": 2401700,
                "garden_like_num": 379,
                "account_type": 30114,
                "birthday": "1992-09-14",
                "hide_value": 0,
                "avatar_frame": 7222,
            },
            "challenge": {
                "player_id": 2222222,
                "challenge_infos": [
                    {"challenge_id": 400003, "use_time": 12521},
                    {"challenge_id": 1052002, "use_time": 40222},
                ],
            },
        },
    ],
    "self_challenge": {
        "player_id": 1234567,
        "challenge_infos": [
            {"challenge_id": 203002, "use_time": 24003},
            {"challenge_id": 1052001, "use_time": 23709},
            {"challenge_id": 302004, "use_time": 8316},
        ],
    },
}
