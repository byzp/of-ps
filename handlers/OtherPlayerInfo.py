from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as OtherPlayerInfoReq_pb2
import proto.OverField_pb2 as OtherPlayerInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as PlayerBriefInfo_pb2
import proto.OverField_pb2 as FriendStatus_pb2
import utils.db as db
import proto.OverField_pb2 as pb

logger = logging.getLogger(__name__)


@packet_handler(CmdId.OtherPlayerInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OtherPlayerInfoReq_pb2.OtherPlayerInfoReq()
        req.ParseFromString(data)

        rsp = OtherPlayerInfoRsp_pb2.OtherPlayerInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        player_id = req.player_id

        other_info = rsp.other_info

        other_info.player_id = db.get_players_info(player_id, "player_id")
        other_info.nick_name = db.get_players_info(player_id, "player_name")
        other_info.level = db.get_players_info(player_id, "level")
        other_info.head = db.get_players_info(player_id, "head")
        other_info.last_login_time = 0
        other_info.sex = db.get_players_info(player_id, "sex")
        other_info.phone_background = db.get_players_info(player_id, "phone_background")
        other_info.is_online = db.get_players_info(player_id, "is_online")
        other_info.sign = db.get_players_info(player_id, "sign")
        other_info.guild_name = db.get_players_info(player_id, "guild_name")
        other_info.character_id = db.get_players_info(player_id, "character_id")
        other_info.create_time = db.get_players_info(player_id, "create_time")
        other_info.player_label = db.get_players_info(player_id, "player_id")
        other_info.garden_like_num = db.get_players_info(player_id, "garden_like_num")
        other_info.account_type = db.get_players_info(player_id, "account_type")
        other_info.birthday = db.get_players_info(player_id, "birthday")
        other_info.hide_value = db.get_players_info(player_id, "hide_value")
        other_info.avatar_frame = db.get_players_info(player_id, "avatar_frame")

        # 获取队长角色ID以及徽章
        team_chars = db.get_players_info(player_id, "team")
        characters = db.get_characters(player_id, team_chars[0])
        character = pb.Character()
        character.ParseFromString(characters[0])
        other_info.team_leader_badge = character.character_appearance.badge
        other_info.character_id = team_chars[0]

        friend_status = db.get_friend_info(
            player_id, session.player_id, "friend_status"
        )
        # 如果好友状态不存在，则响应0
        rsp.friend_status = 0 if friend_status is None else friend_status

        alias = db.get_friend_info(session.player_id, player_id, "alias")
        rsp.alias = alias if alias is not None else ""

        friend_tag = db.get_friend_info(session.player_id, player_id, "friend_tag")
        rsp.friend_tag = friend_tag if friend_tag is not None else 0

        friend_intimacy = db.get_friend_info(
            session.player_id, player_id, "friend_intimacy"
        )
        rsp.friend_intimacy = friend_intimacy if friend_intimacy is not None else 0

        friend_background = db.get_friend_info(
            session.player_id, player_id, "friend_background"
        )
        rsp.friend_background = (
            friend_background if friend_background is not None else 0
        )

        session.send(
            CmdId.OtherPlayerInfoRsp, rsp, packet_id
        )  # 1965 1966 获取其他玩家信息
