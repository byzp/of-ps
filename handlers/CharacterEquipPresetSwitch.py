from server.scene_data import up_scene_action

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    CharacterEquipPresetSwitchReq,
    CharacterEquipPresetSwitchRsp,
    StatusCode,
    ServerSceneSyncDataNotice,
    SceneActionType,
    Character,
    ItemDetail,
)

import utils.db as db
from utils import pb_create


@packet_handler(MsgId.CharacterEquipPresetSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterEquipPresetSwitchReq()
        req.ParseFromString(data)

        rsp = CharacterEquipPresetSwitchRsp()
        rsp.status = StatusCode.StatusCode_OK

        chr_b = db.get_characters(session.player_id, req.char_id)
        if not chr_b:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.CharacterEquipPresetSwitchRsp, rsp, packet_id)
            return
        chr = Character()
        chr.ParseFromString(chr_b[0])
        if req.preset_index >= len(chr.equipment_presets):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.CharacterEquipPresetSwitchRsp, rsp, packet_id)
            return

        old_preset = chr.equipment_presets[chr.in_use_equipment_preset_index]
        chr.in_use_equipment_preset_index = req.preset_index
        new_preset = chr.equipment_presets[req.preset_index]
        db.set_character(session.player_id, req.char_id, chr.SerializeToString())
        rsp.preset_index = req.preset_index
        changed_items = {}

        def _set_wearer(instance_id, wearer):
            if not instance_id:
                return
            blob = db.get_item_detail(session.player_id, None, instance_id)
            if not blob:
                return
            it = ItemDetail()
            it.ParseFromString(blob)
            which = it.main_item.WhichOneof("item")
            sub = getattr(it.main_item, which) if which else None
            if sub is None or not hasattr(sub, "wearer_id"):
                return
            if sub.wearer_id == wearer:
                return
            sub.wearer_id = wearer
            db.set_item_detail(
                session.player_id, it.SerializeToString(), None, instance_id
            )
            changed_items[instance_id] = it

        # 旧方案装备卸下(wearer 清零), 新方案装备穿上(wearer=角色)
        for iid in [old_preset.weapon] + [a.armor_id for a in old_preset.armors]:
            if iid not in (
                [new_preset.weapon] + [a.armor_id for a in new_preset.armors]
            ):
                _set_wearer(iid, 0)
        _set_wearer(new_preset.weapon, req.char_id)
        for a in new_preset.armors:
            _set_wearer(a.armor_id, req.char_id)

        # 返回新方案内的装备详情
        preset = chr.equipment_presets[req.preset_index]
        instance_ids = [preset.weapon]
        instance_ids += [a.armor_id for a in preset.armors]
        instance_ids += [p.poster_id for p in preset.posters]
        current_ids = {instance_id for instance_id in instance_ids if instance_id}
        for instance_id in instance_ids:
            if not instance_id:
                continue
            blob = db.get_item_detail(session.player_id, None, instance_id)
            if blob:
                rsp.items.add().ParseFromString(blob)
        for instance_id, item in changed_items.items():
            if instance_id not in current_ids:
                rsp.items.add().CopyFrom(item)
        # 场景外观同步: 重建场景玩家并广播 UPDATE_APPEARANCE
        pb_create.make_ScenePlayer(session)
        if req.char_id in (session.scene_player.team.char1.char_id,):
            notice = ServerSceneSyncDataNotice()
            notice.status = StatusCode.StatusCode_OK
            entry = notice.data.add()
            entry.player_id = session.player_id
            sd = entry.server_data.add()
            sd.action_type = SceneActionType.SceneActionType_UPDATE_APPEARANCE
            sd.player.CopyFrom(session.scene_player)
            up_scene_action(session.scene_id, session.channel_id, notice)

        session.send(MsgId.CharacterEquipPresetSwitchRsp, rsp, packet_id)  # 1419,1420
