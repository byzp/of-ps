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
from server.scene_data import up_scene_action
from utils import achieve_track
from utils.pb_create import make_SceneTeam
import utils.db as db


@packet_handler(MsgId.CharacterEquipUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterEquipUpdateReq()
        req.ParseFromString(data)
        rsp = CharacterEquipUpdateRsp(status=StatusCode.StatusCode_OK)
        chars = db.get_characters(session.player_id, req.char_id)
        if not chars:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.CharacterEquipUpdateRsp, rsp, packet_id)
            return
        character = Character()
        character.ParseFromString(chars[0])
        new = req.equipment_preset
        old = next(
            (
                p
                for p in character.equipment_presets
                if p.preset_index == new.preset_index
            ),
            None,
        )
        if old is None:
            old = character.equipment_presets.add(preset_index=new.preset_index)
        if new.preset_index != character.in_use_equipment_preset_index:
            old.CopyFrom(new)
            db.set_character(
                session.player_id, req.char_id, character.SerializeToString()
            )
            rsp.character.add().CopyFrom(character)
            session.send(MsgId.CharacterEquipUpdateRsp, rsp, packet_id)
            return
        changed_characters = {req.char_id}
        changes = (
            ("weapon", [old.weapon], [new.weapon], "wear_weapon"),
            (
                "armor",
                [a.armor_id for a in old.armors],
                [a.armor_id for a in new.armors],
                "wear_armor",
            ),
            (
                "poster",
                [p.poster_id for p in old.posters],
                [p.poster_id for p in new.posters],
                "wear_poster",
            ),
        )
        with achieve_track.batch(session):
            for kind, previous, current, event in changes:
                # 槽位移动不能清掉仍穿在同一角色上的实例。
                removed = set(previous) - set(current) - {0}
                added = set(current) - set(previous) - {0}
                for instance_id in sorted(removed | added):
                    item = ItemDetail()
                    item.ParseFromString(
                        db.get_item_detail(session.player_id, None, instance_id)
                    )
                    previous_wearer = getattr(item.main_item, kind).wearer_id
                    if (
                        instance_id in added
                        and previous_wearer
                        and previous_wearer != req.char_id
                    ):
                        previous_character = Character()
                        previous_character.ParseFromString(
                            db.get_characters(session.player_id, previous_wearer)[0]
                        )
                        for preset in previous_character.equipment_presets:
                            if kind == "weapon" and preset.weapon == instance_id:
                                preset.weapon = 0
                            elif kind == "armor":
                                retained = [
                                    a
                                    for a in preset.armors
                                    if a.armor_id != instance_id
                                ]
                                del preset.armors[:]
                                preset.armors.extend(retained)
                            elif kind == "poster":
                                retained = [
                                    p
                                    for p in preset.posters
                                    if p.poster_id != instance_id
                                ]
                                del preset.posters[:]
                                preset.posters.extend(retained)
                        db.set_character(
                            session.player_id,
                            previous_wearer,
                            previous_character.SerializeToString(),
                        )
                        changed_characters.add(previous_wearer)
                        rsp.character.add().CopyFrom(previous_character)
                    getattr(item.main_item, kind).wearer_id = (
                        req.char_id if instance_id in added else 0
                    )
                    db.set_item_detail(
                        session.player_id, item.SerializeToString(), None, instance_id
                    )
                    for index, (stored_id, _) in enumerate(session.temp_pack):
                        if stored_id == instance_id:
                            item.pack_type = ItemDetail.PackType.PackType_TempPack
                            item.main_item.temp_pack_index = index + 1
                            session.temp_pack[index] = (
                                instance_id,
                                item.SerializeToString(),
                            )
                            item.main_item.temp_pack_index = 0
                            break
                    rsp.items.add().CopyFrom(item)
                if added:
                    achieve_track.report(session, event)
            old.CopyFrom(new)
            db.set_character(
                session.player_id, req.char_id, character.SerializeToString()
            )
            result = rsp.character.add(character_id=req.char_id)
            result.equipment_presets.add().CopyFrom(new)
            team = db.get_players_info(session.player_id, "team")[0]
            if changed_characters.intersection(team):
                # 先保存方案再刷新，使用统一场景装备构造覆盖队伍全部位置。
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
