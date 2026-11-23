from proto.net_pb2 import Character as _PbChar

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


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
from utils import achieve_track


@packet_handler(MsgId.UpdateTeamReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdateTeamReq()
        req.ParseFromString(data)

        rsp = UpdateTeamRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 队伍角色必须已拥有(0 表示空位)
        for cid in (req.char1, req.char2, req.char3):
            if cid and not db.get_characters(session.player_id, cid):
                rsp.status = StatusCode.StatusCode_CharNotExist
                session.send(MsgId.UpdateTeamRsp, rsp, packet_id)
                return

        db.set_players_info(
            session.player_id, "team", (req.char1, req.char2, req.char3)
        )
        session.send(MsgId.UpdateTeamRsp, rsp, packet_id)
        # 成就135是当前队伍状态(上阵3名角色)，不是切队操作次数。
        achieve_track.report(
            session,
            "team_size",
            team_size=sum(1 for cid in (req.char1, req.char2, req.char3) if cid),
        )

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
        # 成就: 切换队长(队长变化才计)
        prev = db.get_players_info(session.player_id, "character_id")
        if prev and prev[0] != req.char1:
            achieve_track.report(session, "team_switch")
        db.set_players_info(session.player_id, "character_id", req.char1)
        # 成就: 队长等级36(换队长后按新队长当前等级重判)
        _cap_chars = db.get_characters(session.player_id, req.char1)
        if _cap_chars:

            _cap = _PbChar()
            _cap.ParseFromString(_cap_chars[0])
            achieve_track.captain_level(session, int(_cap.level))

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
