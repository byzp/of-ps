from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as FriendReq_pb2
import proto.OverField_pb2 as FriendRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(CmdId.FriendReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendReq_pb2.FriendReq()
        req.ParseFromString(data)

        rsp = FriendRsp_pb2.FriendRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

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
                other_info.player_id = db.get_players_info(player_id, "player_id")
                other_info.nick_name = db.get_players_info(player_id, "player_name")
                other_info.level = db.get_players_info(player_id, "level")
                other_info.head = db.get_players_info(player_id, "head")
                other_info.last_login_time = 0
                other_info.sex = db.get_players_info(player_id, "sex")
                other_info.phone_background = db.get_players_info(
                    player_id, "phone_background"
                )
                # 通过遍历在线玩家决定在线状态，不从数据库获取
                other_info.is_online = player_id in online_player_ids
                other_info.sign = db.get_players_info(player_id, "sign")
                other_info.guild_name = db.get_players_info(player_id, "guild_name")
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

        session.send(CmdId.FriendRsp, rsp, packet_id)  # 1739,1740
        # session.sbin(CmdId.FriendRsp, "tmp\\bin\\packet_66_1740_servertoclient_body.bin")
