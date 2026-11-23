from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import logging

import pickle

from proto.net_pb2 import (
    Character,
    CharacterAppearance,
    CharacterAppearanceUpdateNotice,
    UpdateCharacterAppearanceReq,
    UpdateCharacterAppearanceRsp,
    StatusCode,
)
import utils.db as db
from utils import achieve_track
from utils.res_loader import res
from server.scene_data import get_session

logger = logging.getLogger(__name__)


"""
# 角色外观更新 2619 2620(广播 2630)
# - umbrella/badge 等字段按请求非默认值覆盖
# - 校验: 角色已拥有 / 雨伞在 Umbrella.umbrella 配置内
# - 广播 CharacterAppearanceUpdateNotice 给同场景频道玩家
"""


@packet_handler(MsgId.UpdateCharacterAppearanceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdateCharacterAppearanceReq()
        req.ParseFromString(data)

        rsp = UpdateCharacterAppearanceRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.char_id = req.char_id

        char_id = req.char_id
        chars = db.get_characters(session.player_id, char_id)

        # 雨伞须在 Umbrella.umbrella 配置内(0=无)
        _umbrellas = {
            u.get("item_i_d")
            for u in res.get("Umbrella", {}).get("umbrella", {}).get("datas", [])
            if isinstance(u, dict)
        }
        if (
            req.HasField("appearance")
            and req.appearance.umbrella_id
            and _umbrellas
            and req.appearance.umbrella_id not in _umbrellas
        ):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.UpdateCharacterAppearanceRsp, rsp, packet_id)
            return

        if not chars:
            rsp.status = StatusCode.StatusCode_CharNotExist
            session.send(MsgId.UpdateCharacterAppearanceRsp, rsp, packet_id)
            return

        character = Character()
        character.ParseFromString(chars[0])

        # 覆盖请求携带的外观字段(非默认值)
        if req.HasField("appearance"):
            appearance = req.appearance
            default_appearance = CharacterAppearance()
            for field_name in Config.UPDATE_CHARACTER_APPEARANCE_FIELDS:
                if getattr(appearance, field_name) != getattr(
                    default_appearance, field_name
                ):
                    setattr(
                        character.character_appearance,
                        field_name,
                        getattr(appearance, field_name),
                    )

        db.set_character(session.player_id, char_id, character.SerializeToString())

        # 成就: 前往时装-更换雨伞(param=2 雨伞位)
        if req.HasField("appearance") and req.appearance.umbrella_id:
            achieve_track.report(session, "change_umbrella", match=2)
        # 成就: 修改队长外观1次(壁纸/勋章等, 仅队长)
        if achieve_track.captain_id(session.player_id) == char_id:
            achieve_track.report(session, "appearance_change")

        # 如果更换的是badge且是队伍1号位, 同步队长徽章列
        if req.HasField("appearance") and req.appearance.badge:
            _team = db.get_players_info(session.player_id, "team") or []
            if _team:
                team_raw = _team[0]
                team_ids = {
                    int(x)
                    for x in str(team_raw).replace(" ", "").split(",")
                    if x.strip().isdigit()
                }
                if char_id in team_ids:
                    db.set_players_info(
                        session.player_id, "badge", req.appearance.badge
                    )

        session.send(MsgId.UpdateCharacterAppearanceRsp, rsp, packet_id)

        # 场景广播外观变更
        notice = CharacterAppearanceUpdateNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.appearance.CopyFrom(character.character_appearance)
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.CharacterAppearanceUpdateNotice, notice, 0)
