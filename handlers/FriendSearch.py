from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as FriendSearchReq_pb2
import proto.OverField_pb2 as FriendSearchRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendSearchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendSearchReq_pb2.FriendSearchReq()
        req.ParseFromString(data)

        rsp = FriendSearchReq_pb2.FriendSearchRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        try:
            player_index = int(req.search_args)
        except Exception as e:
            player_index = ""

        res = False
        if isinstance(player_index, int):
            player_info = db.get_players_info(player_index, "player_id")
            if player_info:
                player_id = player_index
                res = True
        else:
            player_info = db.get_players_info(req.search_args, "player_id")
            if player_info:
                player_id = player_info
                res = True
        if res:
            stat = db.get_friend_info(session.player_id, player_id, "friend_status")
            if stat:
                rsp.friend_status = stat
            other_info = rsp.data
            other_info.player_id = db.get_players_info(player_id, "player_id")
            other_info.nick_name = db.get_players_info(player_id, "player_name")
            other_info.level = db.get_players_info(player_id, "level")
            other_info.head = db.get_players_info(player_id, "head")
            other_info.last_login_time = 0
            other_info.sex = db.get_players_info(player_id, "sex")
            other_info.phone_background = db.get_players_info(
                player_id, "phone_background"
            )
            other_info.is_online = db.get_players_info(player_id, "is_online")
            other_info.sign = db.get_players_info(player_id, "sign")
            other_info.guild_name = db.get_players_info(player_id, "guild_name")
            other_info.team_leader_badge = db.get_players_info(
                player_id, "team_leader_badge"
            )
            other_info.character_id = db.get_players_info(player_id, "character_id")
            other_info.create_time = db.get_players_info(player_id, "create_time")
            other_info.player_label = db.get_players_info(player_id, "player_id")
            other_info.garden_like_num = db.get_players_info(
                player_id, "garden_like_num"
            )
            other_info.account_type = db.get_players_info(player_id, "account_type")
            other_info.birthday = db.get_players_info(player_id, "birthday")
            other_info.hide_value = db.get_players_info(player_id, "hide_value")
            other_info.avatar_frame = db.get_players_info(player_id, "avatar_frame")

        session.send(MsgId.FriendSearchRsp, rsp, packet_id)  # 1739,1740
        # session.sbin(MsgId.FriendRsp, "tmp\\bin\\packet_66_1740_servertoclient_body.bin")
