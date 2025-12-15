from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as FriendIntervalInitReq_pb2
import proto.OverField_pb2 as FriendIntervalInitRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 好友间隙初始化 1841 1842
"""


@packet_handler(MsgId.FriendIntervalInitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendIntervalInitReq_pb2.FriendIntervalInitReq()
        req.ParseFromString(data)

        rsp = FriendIntervalInitRsp_pb2.FriendIntervalInitRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # Set friend_infos data
        for friend_info_data in TEST_DATA["friend_infos"]:
            friend_info = rsp.friend_infos.add()
            friend_info.interval_id = friend_info_data["interval_id"]
            friend_info.finish_time = friend_info_data["finish_time"]
            friend_info.player_id = friend_info_data["player_id"]
            friend_info.create_time = friend_info_data["create_time"]

            # Set member data
            for member_data in friend_info_data["member"]:
                member = friend_info.member.add()
                member.player_id = member_data["player_id"]
                member.nick_name = member_data["nick_name"]
                member.head = member_data["head"]
                member.join_time = member_data["join_time"]
                member.is_reward = member_data["is_reward"]

        # Set join_infos (empty list in this case)
        # for join_info_data in TEST_DATA["join_infos"]:
        #     join_info = rsp.join_infos.add()
        #     # Add join_info fields here if needed

        session.send(MsgId.FriendIntervalInitRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "friend_infos": [
        {
            "interval_id": 103,
            "finish_time": 1763369262656,
            "player_id": 4090368,
            "create_time": 1763343008053,
            "member": [
                {
                    "player_id": 1111111,
                    "nick_name": "测试1",
                    "head": 9011,
                    "join_time": 1763343008053,
                    "is_reward": False,
                }
            ],
        },
        {
            "interval_id": 103,
            "finish_time": 1763364203047,
            "player_id": 1168450,
            "create_time": 1763343905053,
            "member": [
                {
                    "player_id": 2222222,
                    "nick_name": "测试2",
                    "head": 9005,
                    "join_time": 1763348780078,
                    "is_reward": False,
                }
            ],
        },
        {
            "interval_id": 103,
            "finish_time": 1763361057970,
            "player_id": 3333333,
            "create_time": 1763341630053,
            "member": [
                {
                    "player_id": 1732247,
                    "nick_name": "测试3",
                    "head": 9018,
                    "join_time": 1763346656061,
                    "is_reward": False,
                }
            ],
        },
        {
            "interval_id": 103,
            "finish_time": 1763354126295,
            "player_id": 4444444,
            "create_time": 1763335206061,
            "member": [
                {
                    "player_id": 3117960,
                    "nick_name": "测试4",
                    "head": 44102,
                    "join_time": 1763342568078,
                    "is_reward": False,
                }
            ],
        },
    ],
    "join_infos": [],
}
