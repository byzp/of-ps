from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    OutfitPresetUpdateReq,
    OutfitPresetUpdateRsp,
    StatusCode,
    Character,
    OutfitPresetUpdateNotice,
    ServerSceneSyncDataNotice,
    SceneActionType,
)

import utils.db as db
import utils.pb_create as pb_create
from server.scene_data import up_scene_action

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OutfitPresetUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitPresetUpdateReq()
        req.ParseFromString(data)

        rsp = OutfitPresetUpdateRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.char_id = req.char_id
        rsp.preset.CopyFrom(req.preset)
        session.send(MsgId.OutfitPresetUpdateRsp, rsp, packet_id)
        # 更新角色数据
        chr = Character()
        chr.ParseFromString(db.get_characters(session.player_id, req.char_id)[0])
        chr.outfit_presets[req.preset.preset_index].CopyFrom(req.preset)
        db.set_character(session.player_id, req.char_id, chr.SerializeToString())

        rsp = OutfitPresetUpdateNotice()
        rsp.status = StatusCode.StatusCode_OK
        tmp = rsp.chars.add()
        tmp.CopyFrom(chr)
        session.send(MsgId.OutfitPresetUpdateNotice, rsp, packet_id)

        # 广播场景数据
        if req.char_id in db.get_players_info(session.player_id, "team"):
            pb_create.make_ScenePlayer(session)
            sy = ServerSceneSyncDataNotice()
            sy.status = StatusCode.StatusCode_OK
            data = sy.data.add()
            data.player_id = session.player_id
            tmp = data.server_data.add()
            tmp.action_type = SceneActionType.SceneActionType_UPDATE_FASHION
            tmp.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, sy)
