from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import FriendReq, FriendRsp, StatusCode

import utils.db as db
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendReq()
        req.ParseFromString(data)

        rsp = FriendRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 获取在线玩家列表
        online_sessions = get_session()
        online_player_ids = [s.player_id for s in online_sessions]

        for friend_info in db.get_friend_info(
            session.player_id,
            None,
            "friend_id,friend_status,alias,friend_tag,friend_intimacy,friend_background",
        ):
            if req.type == friend_info[1] or req.type == 0:
                info = rsp.info.add()
                info.alias = friend_info[2]
                info.friend_tag = friend_info[3]
                info.friend_intimacy = friend_info[4]
                info.friend_background = friend_info[5]

                other_info = info.info
                player_id = friend_info[0]
                other_info.is_online = player_id in online_player_ids
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
                    other_info.player_label,
                    other_info.garden_like_num,
                    other_info.account_type,
                    other_info.birthday,
                    other_info.hide_value,
                    other_info.avatar_frame,
                ) = db.get_players_info(
                    player_id,
                    "player_id,player_name,level,head,last_login_time,sex,phone_background,sign,guild_name,team_leader_badge,character_id,create_time,player_id,garden_like_num,account_type,birthday,hide_value,avatar_frame",
                )

        session.send(MsgId.FriendRsp, rsp, packet_id)  # 1739,1740
