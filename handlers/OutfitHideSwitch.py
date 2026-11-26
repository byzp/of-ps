from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    OutfitHideSwitchReq,
    OutfitHideSwitchRsp,
    StatusCode,
    ServerSceneSyncDataNotice,
    SceneActionType,
)

from server import character_growth as growth
import utils.db as db
import utils.pb_create as pb_create
from server.scene_data import up_scene_action


@packet_handler(MsgId.OutfitHideSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitHideSwitchReq()
        req.ParseFromString(data)
        rsp = OutfitHideSwitchRsp(status=StatusCode.StatusCode_OK, char_id=req.char_id)
        rsp.hide_info.CopyFrom(req.hide_info)
        try:
            with growth.transaction(session.player_id):
                character = growth.load_character(session.player_id, req.char_id)
                target = next(
                    (
                        preset
                        for preset in character.outfit_presets
                        if preset.preset_index == character.in_use_outfit_preset_index
                    ),
                    None,
                )
                if target is None:
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                target.outfit_hide_info.CopyFrom(req.hide_info)
                growth.save_character(session.player_id, character)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.OutfitHideSwitchRsp, rsp, packet_id)
            return

        session.send(MsgId.OutfitHideSwitchRsp, rsp, packet_id)
        teams = db.get_players_info(session.player_id, "team")
        if teams and req.char_id in teams[0]:
            pb_create.make_ScenePlayer(session)
            notice = ServerSceneSyncDataNotice(status=StatusCode.StatusCode_OK)
            data = notice.data.add()
            data.player_id = session.player_id
            sync = data.server_data.add()
            sync.action_type = SceneActionType.SceneActionType_UPDATE_FASHION
            sync.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, notice)
