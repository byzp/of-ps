from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import FriendSearchReq, FriendSearchRsp, StatusCode

import utils.db as db
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendSearchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendSearchReq()
        req.ParseFromString(data)

        rsp = FriendSearchRsp()
        rsp.status = StatusCode.StatusCode_OK

        try:
            player_index = int(req.search_args)
        except Exception as e:
            player_index = ""

        res = False
        if isinstance(player_index, int):
            player_info = db.get_players_info(player_index, "player_id")
            if player_info:
                player_id = player_index[0]
                res = True
        else:
            player_info = db.get_players_info(req.search_args, "player_id")
            if player_info:
                player_id = player_info[0]
                res = True
        if res:
            other_info = rsp.data
            (
                other_info.player_id,
                other_info.nick_name,
                other_info.level,
                other_info.head,
                other_info.last_login_time,
                other_info.sex,
                other_info.phone_background,
                other_info.sign,
                other_info.guild_name,
                other_info.team_leader_badge,
                other_info.character_id,
                other_info.create_time,
                other_info.garden_like_num,
                other_info.account_type,
                other_info.birthday,
                other_info.hide_value,
                other_info.avatar_frame,
            ) = db.get_players_info(
                player_id,
                "player_id,player_name,level,head,last_login_time,sex,phone_background,sign,guild_name,team_leader_badge,character_id,create_time,garden_like_num,account_type,birthday,hide_value,avatar_frame",
            )
            stat = db.get_friend_info(session.player_id, player_id, "friend_status")[0]
            if stat:
                rsp.friend_status = stat
            other_info.player_label = other_info.player_id
            online_sessions = get_session()
            online_player_ids = [s.player_id for s in online_sessions]
            other_info.is_online = player_id in online_player_ids

        session.send(MsgId.FriendSearchRsp, rsp, packet_id)  # 1739,1740
