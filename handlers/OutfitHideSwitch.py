from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    OutfitHideSwitchReq,
    OutfitHideSwitchRsp,
    StatusCode,
    Character,
    ServerSceneSyncDataNotice,
    SceneActionType,
)

import utils.db as db
import utils.pb_create as pb_create
from server.scene_data import up_scene_action

"""
# 时装隐藏开关(饰品/辫子) 1661 1662
状态持久化在 Character.outfit_presets[当前套装].outfit_hide_info
"""


@packet_handler(MsgId.OutfitHideSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitHideSwitchReq()
        req.ParseFromString(data)

        rsp = OutfitHideSwitchRsp()
        rsp.char_id = req.char_id
        rsp.hide_info.CopyFrom(req.hide_info)

        characters = db.get_characters(session.player_id, req.char_id)
        if not characters:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.OutfitHideSwitchRsp, rsp, packet_id)
            return

        chr = Character()
        chr.ParseFromString(characters[0])
        idx = chr.in_use_outfit_preset_index
        target = None
        for preset in chr.outfit_presets:
            if preset.preset_index == idx:
                target = preset
                break
        if target is None and len(chr.outfit_presets) > idx:
            target = chr.outfit_presets[idx]
        if target is not None:
            target.outfit_hide_info.CopyFrom(req.hide_info)
            db.set_character(session.player_id, req.char_id, chr.SerializeToString())

        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.OutfitHideSwitchRsp, rsp, packet_id)  # 1661,1662

        # 队伍角色广播时装更新(同 OutfitPresetUpdate)
        if req.char_id in db.get_players_info(session.player_id, "team")[0]:
            pb_create.make_ScenePlayer(session)
            sy = ServerSceneSyncDataNotice()
            sy.status = StatusCode.StatusCode_OK
            data_entry = sy.data.add()
            data_entry.player_id = session.player_id
            tmp = data_entry.server_data.add()
            tmp.action_type = SceneActionType.SceneActionType_UPDATE_FASHION
            tmp.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, sy)
