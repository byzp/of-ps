from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import utils.db as db
from proto.net_pb2 import OtherPlayerInfoReq, OtherPlayerInfoRsp, StatusCode
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OtherPlayerInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OtherPlayerInfoReq()
        req.ParseFromString(data)

        rsp = OtherPlayerInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        player_id = req.player_id
        online_sessions = get_session()
        online_player_ids = [s.player_id for s in online_sessions]

        other_info = rsp.other_info

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

        friend_info = db.get_friend_info(
            player_id,
            session.player_id,
            "friend_status,alias,friend_tag,friend_intimacy,friend_background",
        )
        if friend_info[0] != None:
            (
                rsp.friend_status,
                rsp.alias,
                rsp.friend_tag,
                rsp.friend_intimacy,
                rsp.friend_background,
            ) = friend_info
        if (
            db.get_friend_info(session.player_id, req.player_id, "friend_status")[0]
            == 3
        ):
            # 任意一方黑名单都导致双方不可加好友
            rsp.friend_status = 3
        session.send(
            MsgId.OtherPlayerInfoRsp, rsp, packet_id
        )  # 1965 1966 获取其他玩家信息
