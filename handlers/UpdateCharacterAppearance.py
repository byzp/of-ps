from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as UpdateCharacterAppearanceReq_pb2
import proto.OverField_pb2 as UpdateCharacterAppearanceRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb
import utils.db as db
import utils.pb_create as pb_create
from server.scene_data import up_scene_action

logger = logging.getLogger(__name__)


@packet_handler(CmdId.UpdateCharacterAppearanceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdateCharacterAppearanceReq_pb2.UpdateCharacterAppearanceReq()
        req.ParseFromString(data)

        char_id = req.char_id

        characters = db.get_characters(session.player_id, char_id)
        if not characters:
            rsp = UpdateCharacterAppearanceRsp_pb2.UpdateCharacterAppearanceRsp()
            rsp.status = StatusCode_pb2.StatusCode_Error
            session.send(CmdId.UpdateCharacterAppearanceRsp, rsp, packet_id)
            return

        character = pb.Character()
        character.ParseFromString(characters[0])

        if req.HasField("appearance"):
            appearance = req.appearance
            default_appearance = pb.CharacterAppearance()
            fields_to_check = [
                "badge",
                "umbrella_id",
                "insect_net_instance_id",
                "logging_axe_instance_id",
                "water_bottle_instance_id",
                "mining_hammer_instance_id",
                "collection_gloves_instance_id",
                "fishing_rod_instance_id",
            ]
            for field_name in fields_to_check:
                if getattr(appearance, field_name) != getattr(
                    default_appearance, field_name
                ):
                    setattr(
                        character.character_appearance,
                        field_name,
                        getattr(appearance, field_name),
                    )

        db.set_character(session.player_id, char_id, character.SerializeToString())

        rsp = UpdateCharacterAppearanceRsp_pb2.UpdateCharacterAppearanceRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.char_id = char_id
        rsp.appearance.badge = req.appearance.badge
        rsp.appearance.umbrella_id = req.appearance.umbrella_id
        rsp.appearance.insect_net_instance_id = req.appearance.insect_net_instance_id
        rsp.appearance.logging_axe_instance_id = req.appearance.logging_axe_instance_id
        rsp.appearance.water_bottle_instance_id = (
            req.appearance.water_bottle_instance_id
        )
        rsp.appearance.mining_hammer_instance_id = (
            req.appearance.mining_hammer_instance_id
        )
        rsp.appearance.collection_gloves_instance_id = (
            req.appearance.collection_gloves_instance_id
        )
        rsp.appearance.fishing_rod_instance_id = req.appearance.fishing_rod_instance_id

        session.send(CmdId.UpdateCharacterAppearanceRsp, rsp, packet_id)

        # 如果更换的是badge且req.char_id是队伍角色1，更新数据库的队长徽章ID
        team = db.get_players_info(session.player_id, "team")
        if (req.HasField("appearance") and 
            hasattr(req.appearance, "badge") and 
            team and 
            len(team) > 0 and 
            char_id == team[0]):
            db.set_players_info(
                session.player_id, "team_leader_badge", req.appearance.badge
            )

        # 发送场景同步通知
        if char_id in db.get_players_info(session.player_id, "team"):
            session.scene_player.team.char_1.character_appearance.CopyFrom(
                req.appearance
            )
            notice = pb.ServerSceneSyncDataNotice()
            notice.status = StatusCode_pb2.StatusCode_OK
            data_entry = notice.data.add()
            data_entry.player_id = session.player_id
            server_data_entry = data_entry.server_data.add()
            server_data_entry.action_type = pb.SceneActionType_UPDATE_APPEARANCE
            server_data_entry.player.CopyFrom(session.scene_player)
            up_scene_action(
                session.scene_id, session.channel_id, notice.SerializeToString()
            )
