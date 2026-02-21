from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    CharacterGatherWeaponUpdateReq,
    CharacterGatherWeaponUpdateRsp,
    StatusCode,
    Character,
    ServerSceneSyncDataNotice,
    SceneActionType,
)

import utils.db as db
from server.scene_data import up_scene_action

logger = logging.getLogger(__name__)


@packet_handler(MsgId.CharacterGatherWeaponUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterGatherWeaponUpdateReq()
        req.ParseFromString(data)

        character_id = req.character_id
        weapon_id = req.weapon_id

        character_data = db.get_characters(session.player_id, character_id)
        if not character_data:
            rsp = CharacterGatherWeaponUpdateRsp()
            rsp.status = StatusCode.StatusCode_INTERNAL_ERROR
            session.send(MsgId.CharacterGatherWeaponUpdateRsp, rsp, packet_id)
            return

        character = Character()
        character.ParseFromString(character_data[0])
        character.gather_weapon = weapon_id

        db.set_character(session.player_id, character_id, character.SerializeToString())

        # 场景同步
        if character_id in db.get_players_info(session.player_id, "team"):
            session.scene_player.team.char1.gather_weapon = weapon_id

            sy = ServerSceneSyncDataNotice()
            sy.status = StatusCode.StatusCode_OK

            data = sy.data.add()
            data.player_id = session.player_id
            tmp = data.server_data.add()
            tmp.action_type = (
                SceneActionType.SceneActionType_UPDATE_EQUIP
            )  # 使用装备更新枚举
            tmp.player.CopyFrom(session.scene_player)

            up_scene_action(session.scene_id, session.channel_id, sy)

        rsp = CharacterGatherWeaponUpdateRsp()
        rsp.status = StatusCode.StatusCode_OK

        session.send(
            MsgId.CharacterGatherWeaponUpdateRsp, rsp, packet_id
        )  # 1955 1956 采集武器更新
