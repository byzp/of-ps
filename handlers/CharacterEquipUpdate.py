from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    CharacterEquipUpdateReq,
    CharacterEquipUpdateRsp,
    Character,
    ItemDetail,
    StatusCode,
    ServerSceneSyncDataNotice,
    SceneActionType,
)
from server import character_growth as growth
from server.scene_data import up_scene_action
from utils import achieve_track
from utils.pb_create import make_SceneTeam
import utils.db as db


def _ids(preset):
    return (
        ("weapon", (preset.weapon,)),
        ("armor", tuple(item.armor_id for item in preset.armors)),
        ("poster", tuple(item.poster_id for item in preset.posters)),
    )


def _detach(character, instance_id, kind):
    for preset in character.equipment_presets:
        if kind == "weapon" and preset.weapon == instance_id:
            preset.weapon = 0
        elif kind == "armor":
            retained = [item for item in preset.armors if item.armor_id != instance_id]
            del preset.armors[:]
            preset.armors.extend(retained)
        elif kind == "poster":
            retained = [item for item in preset.posters if item.poster_id != instance_id]
            del preset.posters[:]
            preset.posters.extend(retained)


@packet_handler(MsgId.CharacterEquipUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterEquipUpdateReq()
        req.ParseFromString(data)
        rsp = CharacterEquipUpdateRsp(status=StatusCode.StatusCode_OK)
        new = req.equipment_preset
        changed_items = {}
        changed_characters = set()
        worn_events = []
        try:
            with growth.transaction(session.player_id):
                character = growth.load_character(session.player_id, req.char_id)
                if new.preset_index >= Config.EQUIPMENT_PRESET_LIMIT:
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                armor_types = [item.equip_type for item in new.armors]
                poster_slots = [item.poster_index for item in new.posters]
                if len(set(armor_types)) != len(armor_types) or any(
                    value not in (1, 2, 3) for value in armor_types
                ):
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                if len(set(poster_slots)) != len(poster_slots) or any(
                    value not in (0, 1, 2) for value in poster_slots
                ):
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)

                loaded = {}
                seen = set()
                for kind, instance_ids in _ids(new):
                    for instance_id in instance_ids:
                        if not instance_id:
                            continue
                        if instance_id in seen:
                            raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                        seen.add(instance_id)
                        loaded[instance_id] = growth.load_owned_instance(
                            session.player_id, instance_id, kind
                        )
                old = next(
                    (item for item in character.equipment_presets if item.preset_index == new.preset_index),
                    None,
                )
                if old is None:
                    old = character.equipment_presets.add(preset_index=new.preset_index)

                if new.preset_index != character.in_use_equipment_preset_index:
                    for kind, instance_ids in _ids(new):
                        for instance_id in instance_ids:
                            if instance_id and getattr(
                                loaded[instance_id].main_item, kind
                            ).wearer_id not in (0, req.char_id):
                                raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                    old.CopyFrom(new)
                    growth.save_character(session.player_id, character)
                    rsp.character.add().CopyFrom(character)
                else:
                    changes = []
                    for kind, previous_ids, current_ids, event in (
                        ("weapon", (old.weapon,), (new.weapon,), "wear_weapon"),
                        (
                            "armor",
                            tuple(item.armor_id for item in old.armors),
                            tuple(item.armor_id for item in new.armors),
                            "wear_armor",
                        ),
                        (
                            "poster",
                            tuple(item.poster_id for item in old.posters),
                            tuple(item.poster_id for item in new.posters),
                            "wear_poster",
                        ),
                    ):
                        removed = set(previous_ids) - set(current_ids) - {0}
                        added = set(current_ids) - set(previous_ids) - {0}
                        changes.append((kind, removed, added, event))
                    for kind, removed, added, event in changes:
                        for instance_id in sorted(removed | added):
                            detail = loaded.get(instance_id)
                            if detail is None:
                                detail = growth.load_owned_instance(
                                    session.player_id, instance_id, kind
                                )
                            state = getattr(detail.main_item, kind)
                            if instance_id in added and state.wearer_id not in (0, req.char_id):
                                previous_id = state.wearer_id
                                previous = growth.load_character(session.player_id, previous_id)
                                _detach(previous, instance_id, kind)
                                growth.save_character(session.player_id, previous)
                                changed_characters.add(previous_id)
                                rsp.character.add().CopyFrom(previous)
                            state.wearer_id = req.char_id if instance_id in added else 0
                            db.set_item_detail(
                                session.player_id,
                                detail.SerializeToString(),
                                None,
                                instance_id,
                            )
                            changed_items[instance_id] = detail
                        if added:
                            worn_events.append(event)
                    old.CopyFrom(new)
                    growth.save_character(session.player_id, character)
                    changed_characters.add(req.char_id)
                    result = rsp.character.add(character_id=req.char_id)
                    result.equipment_presets.add().CopyFrom(new)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.CharacterEquipUpdateRsp, rsp, packet_id)
            return

        for instance_id, detail in changed_items.items():
            detail.pack_type = ItemDetail.PackType.PackType_Inventory
            detail.main_item.temp_pack_index = 0
            rsp.items.add().CopyFrom(detail)
            for index, (stored_id, _) in enumerate(session.temp_pack):
                if stored_id == instance_id:
                    detail.pack_type = ItemDetail.PackType.PackType_TempPack
                    detail.main_item.temp_pack_index = index + 1
                    session.temp_pack[index] = (instance_id, detail.SerializeToString())
                    detail.pack_type = ItemDetail.PackType.PackType_Inventory
                    detail.main_item.temp_pack_index = 0
                    break
        for event in worn_events:
            achieve_track.report(session, event)

        teams = db.get_players_info(session.player_id, "team")
        team = teams[0] if teams else ()
        if changed_characters.intersection(team):
            updated = make_SceneTeam(session.player_id, team)
            for field in ("char1", "char2", "char3"):
                target = getattr(session.scene_player.team, field)
                if target.char_id in changed_characters:
                    source = getattr(updated, field)
                    target.weapon_id = source.weapon_id
                    target.weapon_star = source.weapon_star
                    target.armors.clear()
                    target.armors.extend(source.armors)
                    target.posters.clear()
                    target.posters.extend(source.posters)
            notice = ServerSceneSyncDataNotice(status=StatusCode.StatusCode_OK)
            sync = notice.data.add(player_id=session.player_id).server_data.add()
            sync.action_type = SceneActionType.SceneActionType_UPDATE_EQUIP
            sync.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, notice)
        session.send(MsgId.CharacterEquipUpdateRsp, rsp, packet_id)
