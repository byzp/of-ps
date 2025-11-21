from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as OutfitPresetUpdateReq_pb2
import proto.OverField_pb2 as OutfitPresetUpdateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import utils.db as db
import utils.pb_create as pb_create
from server.scene_data import up_scene_action

logger = logging.getLogger(__name__)


@packet_handler(CmdId.OutfitPresetUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitPresetUpdateReq_pb2.OutfitPresetUpdateReq()
        req.ParseFromString(data)

        rsp = OutfitPresetUpdateRsp_pb2.OutfitPresetUpdateRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.char_id = req.char_id
        rsp.preset.CopyFrom(req.preset)
        session.send(CmdId.OutfitPresetUpdateRsp, rsp, False, packet_id)
        # 更新角色数据
        chr = pb.Character()
        chr.ParseFromString(db.get_characters(session.player_id, req.char_id)[0])
        chr.outfit_presets[req.preset.preset_index].CopyFrom(req.preset)
        db.up_character(session.player_id, req.char_id, chr.SerializeToString())

        rsp = pb.OutfitPresetUpdateNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        tmp = rsp.chars.add()
        tmp.CopyFrom(chr)
        session.send(CmdId.OutfitPresetUpdateNotice, rsp, False, packet_id)

        # 广播场景数据
        if req.char_id in db.get_team_char_id(session.player_id):
            pb_create.make_ScenePlayer(session)
            sy = pb.ServerSceneSyncDataNotice()
            sy.status = StatusCode_pb2.StatusCode_OK
            data = sy.data.add()
            data.player_id = session.player_id
            tmp = data.server_data.add()
            tmp.action_type = pb.SceneActionType_UPDATE_FASHION
            tmp.player.CopyFrom(session.scene_player)
            up_scene_action(
                session.scene_id, session.channel_id, sy.SerializeToString()
            )
