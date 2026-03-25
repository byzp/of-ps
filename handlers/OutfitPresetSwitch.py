from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    OutfitPresetSwitchReq,
    OutfitPresetSwitchRsp,
    StatusCode,
    Character,
    ServerSceneSyncDataNotice,
    SceneActionType,
)
import utils.db as db
import utils.pb_create as pb_create
from server.scene_data import up_scene_action

logger = logging.getLogger(__name__)


@packet_handler(MsgId.OutfitPresetSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitPresetSwitchReq()
        req.ParseFromString(data)

        rsp = OutfitPresetSwitchRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.char_id = req.char_id
        rsp.use_preset_index = req.use_preset_index
        session.send(MsgId.OutfitPresetSwitchRsp, rsp, packet_id)

        chr = Character()
        chr.ParseFromString(db.get_characters(session.player_id, req.char_id)[0])
        chr.in_use_outfit_preset_index = req.use_preset_index
        db.set_character(session.player_id, req.char_id, chr.SerializeToString())

        # 广播场景数据
        if req.char_id in db.get_players_info(session.player_id, "team")[0]:
            pb_create.make_ScenePlayer(session)
            sy = ServerSceneSyncDataNotice()
            sy.status = StatusCode.StatusCode_OK
            data = sy.data.add()
            data.player_id = session.player_id
            tmp = data.server_data.add()
            tmp.action_type = SceneActionType.SceneActionType_UPDATE_FASHION
            tmp.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, sy)
