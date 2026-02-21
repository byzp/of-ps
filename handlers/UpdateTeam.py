from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    UpdateTeamReq,
    UpdateTeamRsp,
    StatusCode,
    Character,
    ServerSceneSyncDataNotice,
    SceneActionType,
)
from server.scene_data import up_scene_action
import utils.pb_create as pb_create

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.UpdateTeamReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdateTeamReq()
        req.ParseFromString(data)

        rsp = UpdateTeamRsp()
        rsp.status = StatusCode.StatusCode_OK

        db.set_players_info(
            session.player_id, "team", (req.char1, req.char2, req.char3)
        )
        session.send(MsgId.UpdateTeamRsp, rsp, packet_id)

        # 修改玩家 队长徽章ID
        characters = db.get_characters(session.player_id, req.char1)
        if characters:
            character = Character()
            character.ParseFromString(characters[0])
            db.set_players_info(
                session.player_id,
                "team_leader_badge",
                character.character_appearance.badge,
            )
        # 修改玩家 队长角色ID
        db.set_players_info(session.player_id, "character_id", req.char1)

        # 发送场景同步通知
        pb_create.make_ScenePlayer(session)
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.player_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = SceneActionType.SceneActionType_UPDATE_TEAM

        server_data_entry.player.CopyFrom(session.scene_player)
        up_scene_action(session.scene_id, session.channel_id, notice)
