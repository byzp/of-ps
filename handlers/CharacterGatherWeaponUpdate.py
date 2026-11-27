from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    CharacterGatherWeaponUpdateReq,
    CharacterGatherWeaponUpdateRsp,
    StatusCode,
    ServerSceneSyncDataNotice,
    SceneActionType,
)

from server import character_growth as growth
from server.scene_data import up_scene_action
import utils.db as db


@packet_handler(MsgId.CharacterGatherWeaponUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterGatherWeaponUpdateReq()
        req.ParseFromString(data)
        rsp = CharacterGatherWeaponUpdateRsp(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                character = growth.load_character(session.player_id, req.character_id)
                if req.weapon_id:
                    cfg = next(
                        (
                            row
                            for row in growth.rows("Weapon", "weapon")
                            if row.get("i_d") == req.weapon_id
                            and int(row.get("new_weapon_system_type", 0) or 0) == 6
                        ),
                        None,
                    )
                    if cfg is None:
                        raise growth.GrowthError(
                            StatusCode.StatusCode_GATHER_WEAPON_TYPE_DIFFER
                        )
                character.gather_weapon = req.weapon_id
                growth.save_character(session.player_id, character)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.CharacterGatherWeaponUpdateRsp, rsp, packet_id)
            return

        teams = db.get_players_info(session.player_id, "team")
        team = teams[0] if teams else ()
        if req.character_id in team:
            for field in ("char1", "char2", "char3"):
                target = getattr(session.scene_player.team, field)
                if target.char_id == req.character_id:
                    target.gather_weapon = req.weapon_id
            notice = ServerSceneSyncDataNotice(status=StatusCode.StatusCode_OK)
            data = notice.data.add()
            data.player_id = session.player_id
            sync = data.server_data.add()
            sync.action_type = SceneActionType.SceneActionType_UPDATE_EQUIP
            sync.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, notice)
        session.send(MsgId.CharacterGatherWeaponUpdateRsp, rsp, packet_id)
