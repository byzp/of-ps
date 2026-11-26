import json as _json

from proto.net_pb2 import Character as PbChar

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    GardenPlaceCharacterReq,
    GardenPlaceCharacterRsp,
    GardenPlaceCharacterNotice,
    FurnitureDetailsInfo,
    ScenePlacedCharacter,
    StatusCode,
)
from utils.res_loader import res
import utils.db as db
from utils.pb_create import (
    make_SceneCharacterOutfitPreset,
    _effective_outfit_preset,
)
from server import scene_data

"""
# 放置角色到花园家具 2625 2626(广播 2628)
# 校验: 家具已摆放/角色已拥有/不在当前队伍/座位未被占/角色未被他座占用
# 持久化: kv ns=garden key=placements  {"furniture_id:seat_id": character_id}
# 进花园/查花园信息时由 replay_placements 重放通知
"""


def load_placements(player_id):

    raw = db.get_kv(player_id, "garden", "placements", b"")
    if not raw:
        return {}
    return _json.loads(raw.decode())


def save_placements(player_id, placements):

    db.set_kv(
        player_id,
        "garden",
        "placements",
        _json.dumps(placements).encode(),
    )


def _placed_notice(player_id, character_id, furniture_id, seat_id, remove=False):
    """构造单条放置/移除通知(含角色当前外观预设)"""
    notice = GardenPlaceCharacterNotice()
    notice.status = StatusCode.StatusCode_OK
    if remove:
        notice.remove_character_id = character_id
        return notice
    ch = ScenePlacedCharacter()
    ch.character_id = character_id
    ch.furniture_id = furniture_id
    ch.seat_id = seat_id
    chars = db.get_characters(player_id, character_id)
    if chars:

        c = PbChar()
        c.ParseFromString(chars[0])
        preset = _effective_outfit_preset(c)
        if preset is not None:
            make_SceneCharacterOutfitPreset(player_id, preset, ch.outfit_preset)
    notice.character.CopyFrom(ch)
    return notice


def replay_placements(session):
    """进入花园/打开花园面板时重放全部已放置角色(客户端恢复椅子上的角色)"""
    placements = load_placements(session.player_id)
    for seat_key, character_id in sorted(placements.items()):
        parts = seat_key.split(":")
        if len(parts) != 2 or not all(p.isdecimal() for p in parts):
            continue
        furniture_id, seat_id = int(parts[0]), int(parts[1])
        notice = _placed_notice(
            session.player_id, int(character_id), furniture_id, seat_id
        )
        session.send(MsgId.GardenPlaceCharacterNotice, notice, 0)


@packet_handler(MsgId.GardenPlaceCharacterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenPlaceCharacterReq()
        req.ParseFromString(data)

        rsp = GardenPlaceCharacterRsp()
        if session.scene_id != 9999 or session.channel_id != session.player_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        rsp.character_id = req.character_id
        rsp.furniture_id = req.furniture_id
        rsp.seat_id = req.seat_id
        rsp.is_remove = req.is_remove

        placements = load_placements(session.player_id)
        seat_key = f"{req.furniture_id}:{req.seat_id}"

        if req.is_remove:
            removed = placements.pop(seat_key, None)
            save_placements(session.player_id, placements)
            if removed is None:
                rsp.status = StatusCode.StatusCode_FURNITURE_NOT_EXIST
                session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
                return
        elif req.character_id:
            # 家具必须已摆放在花园中
            furniture_row = db.get_furniture(
                session.scene_id,
                session.channel_id,
                session.player_id,
                req.furniture_id,
            )
            if not furniture_row:
                rsp.status = StatusCode.StatusCode_FURNITURE_NOT_EXIST
                session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
                return
            furniture = FurnitureDetailsInfo()
            furniture.ParseFromString(furniture_row[-1])
            seat_limit = next(
                (int(row.get('home_item_point_num', 0)) for row in res['HomeItem']['home_item']['datas'] if row.get('item_i_d') == furniture.furniture_item_id),
                0,
            )
            if seat_limit and not 0 <= req.seat_id < seat_limit:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
                return
            # 角色必须已拥有
            chars = db.get_characters(session.player_id, req.character_id)
            if not chars:
                rsp.status = (
                    StatusCode.StatusCode_GARDEN_PLACE_CHARACTER_CONDITION_NOT_MET
                )
                session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
                return
            # 不能与当前队伍角色重复(角色正在队伍中)
            team_info = db.get_players_info(session.player_id, "team")
            raw_team = team_info[0] if team_info else ()
            if isinstance(raw_team, (tuple, list)):
                team_ids = {int(value) for value in raw_team if value}
            elif isinstance(raw_team, bytes):
                import pickle
                team_ids = {int(value) for value in pickle.loads(raw_team) if value}
            else:
                team_ids = {int(value) for value in str(raw_team).replace('(', '').replace(')', '').replace(' ', '').split(',') if value.isdigit()}
            if req.character_id in team_ids:
                rsp.status = StatusCode.StatusCode_CHARACTER_IN_TEAM
                session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
                return
            # 角色已被放置在其他座位
            for other_key, other_cid in placements.items():
                if other_cid == req.character_id and other_key != seat_key:
                    rsp.status = StatusCode.StatusCode_CHARACTER_PLACED
                    session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
                    return
            # 座位已被其他角色占用
            occupant = placements.get(seat_key)
            if occupant and int(occupant) != req.character_id:
                rsp.status = StatusCode.StatusCode_FURNITURE_OCCUPY
                session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
                return
            placements[seat_key] = req.character_id
            save_placements(session.player_id, placements)
        else:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)
            return

        session.send(MsgId.GardenPlaceCharacterRsp, rsp, packet_id)

        # 广播放置/移除通知(同花园场景频道所有玩家, 含自己)
        notice = _placed_notice(
            session.player_id,
            req.character_id,
            req.furniture_id,
            req.seat_id,
            remove=req.is_remove,
        )
        for s in scene_data.get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.GardenPlaceCharacterNotice, notice, 0)
