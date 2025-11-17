from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.net_pb2 as OtherPlayerInfoReq_pb2
import proto.net_pb2 as OtherPlayerInfoRsp_pb2
import proto.net_pb2 as StatusCode_pb2
import proto.net_pb2 as PlayerBriefInfo_pb2
import proto.net_pb2 as FriendStatus_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.OtherPlayerInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OtherPlayerInfoReq_pb2.OtherPlayerInfoReq()
        req.ParseFromString(data)

        rsp = OtherPlayerInfoRsp_pb2.OtherPlayerInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set fields from hardcoded test data, but use player_id from request
        rsp.status = TEST_DATA["status"]
        
        # Set other_info
        other_info = PlayerBriefInfo_pb2.PlayerBriefInfo()
        # Use player_id from the request
        other_info.player_id = req.player_id
        other_info.nick_name = TEST_DATA["other_info"]["nick_name"]
        other_info.level = TEST_DATA["other_info"]["level"]
        other_info.head = TEST_DATA["other_info"]["head"]
        other_info.last_login_time = TEST_DATA["other_info"]["last_login_time"]
        other_info.team_leader_badge = TEST_DATA["other_info"]["team_leader_badge"]
        other_info.sex = TEST_DATA["other_info"]["sex"]
        other_info.phone_background = TEST_DATA["other_info"]["phone_background"]
        other_info.is_online = TEST_DATA["other_info"]["is_online"]
        other_info.sign = TEST_DATA["other_info"]["sign"]
        other_info.guild_name = TEST_DATA["other_info"]["guild_name"]
        other_info.character_id = TEST_DATA["other_info"]["character_id"]
        other_info.create_time = TEST_DATA["other_info"]["create_time"]
        other_info.player_label = TEST_DATA["other_info"]["player_label"]
        other_info.garden_like_num = TEST_DATA["other_info"]["garden_like_num"]
        other_info.account_type = TEST_DATA["other_info"]["account_type"]
        other_info.birthday = TEST_DATA["other_info"]["birthday"]
        other_info.hide_value = TEST_DATA["other_info"]["hide_value"]
        other_info.avatar_frame = TEST_DATA["other_info"]["avatar_frame"]
        rsp.other_info.CopyFrom(other_info)
        
        # Set other fields
        rsp.friend_status = TEST_DATA["friend_status"]
        rsp.alias = TEST_DATA["alias"]
        rsp.friend_tag = TEST_DATA["friend_tag"]
        rsp.friend_intimacy = TEST_DATA["friend_intimacy"]
        rsp.friend_background = TEST_DATA["friend_background"]

        session.send(CmdId.OtherPlayerInfoRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "other_info": {
        "player_id": 1234567,
        "nick_name": "测试123",
        "level": 50,
        "head": 9330,
        "last_login_time": 0,
        "team_leader_badge": 5000,
        "sex": 0,
        "phone_background": 8027,
        "is_online": True,
        "sign": "测试1234567",
        "guild_name": "",
        "character_id": 201002,
        "create_time": 1743490564,
        "player_label": 2417364,
        "garden_like_num": 31460,
        "account_type": 28814,
        "birthday": "1992-11-11",
        "hide_value": 0,
        "avatar_frame": 7235
    },
    "friend_status": 2,
    "alias": "",
    "friend_tag": 0,
    "friend_intimacy": 0,
    "friend_background": 0
}