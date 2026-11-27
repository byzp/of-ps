from server.scene_data import up_scene_action

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    CharacterEquipPresetSwitchReq,
    CharacterEquipPresetSwitchRsp,
    StatusCode,
    ServerSceneSyncDataNotice,
    SceneActionType,
    ItemDetail,
)
from config import Config

from server import character_growth as growth
from utils import pb_create
import utils.db as db


def _ids(preset):
    return (
        ("weapon", (preset.weapon,)),
        ("armor", tuple(item.armor_id for item in preset.armors)),
        ("poster", tuple(item.poster_id for item in preset.posters)),
    )


@packet_handler(MsgId.CharacterEquipPresetSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterEquipPresetSwitchReq()
        req.ParseFromString(data)
        rsp = CharacterEquipPresetSwitchRsp(status=StatusCode.StatusCode_OK)
        changed_items = {}
        try:
            with growth.transaction(session.player_id):
                character = growth.load_character(session.player_id, req.char_id)
                if req.preset_index >= Config.EQUIPMENT_PRESET_LIMIT:
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                old = next(
                    (
                        preset
                        for preset in character.equipment_presets
                        if preset.preset_index == character.in_use_equipment_preset_index
                    ),
                    None,
                )
                new = next(
                    (
                        preset
                        for preset in character.equipment_presets
                        if preset.preset_index == req.preset_index
                    ),
                    None,
                )
                if old is None or new is None:
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                old_ids = {
                    instance_id
                    for _, ids in _ids(old)
                    for instance_id in ids
                    if instance_id
                }
                new_ids = {
                    instance_id
                    for _, ids in _ids(new)
                    for instance_id in ids
                    if instance_id
                }
                if len(new_ids) != sum(len(ids) for _, ids in _ids(new)):
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                for instance_id in new_ids:
                    kind = next(
                        kind
                        for kind, ids in _ids(new)
                        if instance_id in ids
                    )
                    detail = growth.load_owned_instance(session.player_id, instance_id, kind)
                    wearer = getattr(detail.main_item, kind).wearer_id
                    if wearer not in (0, req.char_id):
                        raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                for instance_id in old_ids - new_ids:
                    kind = next(
                        kind
                        for kind, ids in _ids(old)
                        if instance_id in ids
                    )
                    detail = growth.load_owned_instance(session.player_id, instance_id, kind)
                    state = getattr(detail.main_item, kind)
                    if state.wearer_id not in (0, req.char_id):
                        raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                    state.wearer_id = 0
                    db.set_item_detail(
                        session.player_id, detail.SerializeToString(), None, instance_id
                    )
                    changed_items[instance_id] = detail
                for instance_id in new_ids:
                    kind = next(kind for kind, ids in _ids(new) if instance_id in ids)
                    detail = growth.load_owned_instance(session.player_id, instance_id, kind)
                    state = getattr(detail.main_item, kind)
                    state.wearer_id = req.char_id
                    db.set_item_detail(
                        session.player_id, detail.SerializeToString(), None, instance_id
                    )
                    changed_items[instance_id] = detail
                character.in_use_equipment_preset_index = req.preset_index
                growth.save_character(session.player_id, character)
                rsp.preset_index = req.preset_index
                for detail in changed_items.values():
                    rsp.items.add().CopyFrom(detail)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.CharacterEquipPresetSwitchRsp, rsp, packet_id)
            return

        pb_create.make_ScenePlayer(session)
        teams = db.get_players_info(session.player_id, "team")
        team = teams[0] if teams else ()
        if any(
            getattr(session.scene_player.team, field).char_id == req.char_id
            for field in ("char1", "char2", "char3")
        ):
            notice = ServerSceneSyncDataNotice(status=StatusCode.StatusCode_OK)
            entry = notice.data.add()
            entry.player_id = session.player_id
            sd = entry.server_data.add()
            sd.action_type = SceneActionType.SceneActionType_UPDATE_APPEARANCE
            sd.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, notice)
        session.send(MsgId.CharacterEquipPresetSwitchRsp, rsp, packet_id)
