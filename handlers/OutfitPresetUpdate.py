from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    OutfitPresetUpdateReq,
    OutfitPresetUpdateRsp,
    StatusCode,
    Character,
    ServerSceneSyncDataNotice,
    SceneActionType,
)

import logging

import utils.db as db
from utils.trace import trace
import utils.pb_create as pb_create
from server.scene_data import up_scene_action
from utils import achieve_track

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
        # 成就: 更换时装127(方案含任意外观槽位即计);
        # 雨伞144 无独立上报通道不计数

        preset = req.preset
        if preset.clothes or preset.hat or preset.hair or preset.ornament:
            achieve_track.report(session, "wear_outfit")
        trace("preset_update", player=session.player_id, char=req.char_id,
              idx=req.preset.preset_index, hat=req.preset.hat, hair=req.preset.hair,
              clothes=req.preset.clothes, ornament=req.preset.ornament, status=rsp.status)
        session.send(MsgId.OutfitPresetUpdateRsp, rsp, packet_id)
        # 更新角色数据
        chars = db.get_characters(session.player_id, req.char_id)
        if not chars:
            logger.warning(
                "OutfitPresetUpdate: player=%s 没有角色 %s", session.player_id, req.char_id
            )
            return
        chr = Character()
        chr.ParseFromString(chars[0])
        # 原来直接按 preset_index 当下标取, 客户端给的序号超出列表长度就 IndexError,
        # 整个包被兜底成 status=2 空包 -> 客户端崩溃/掉线。这里按字段匹配, 找不到就追加。
        _target = None
        for _p in chr.outfit_presets:
            if _p.preset_index == req.preset.preset_index:
                _target = _p
                break
        if _target is None:
            _target = chr.outfit_presets.add()
        _target.CopyFrom(req.preset)
        db.set_character(session.player_id, req.char_id, chr.SerializeToString())
        logger.info(
            "OutfitPresetUpdate: player=%s char=%s preset_index=%s hat=%s hair=%s clothes=%s ornament=%s clothes_dye=%s",
            session.player_id,
            req.char_id,
            req.preset.preset_index,
            req.preset.hat,
            req.preset.hair,
            req.preset.clothes,
            req.preset.ornament,
            req.preset.clothes_dye_scheme_index,
        )

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
