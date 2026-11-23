from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TempPackWearEquipReq,
    TempPackWearEquipRsp,
    StatusCode,
    ItemDetail,
    Character,
    PackNotice,
    EBagItemTag,
    ServerSceneSyncDataNotice,
    SceneActionType,
)

import utils.db as db
from utils import item_mgr
from server.scene_data import up_scene_action
from utils.res_loader import res


@packet_handler(MsgId.TempPackWearEquipReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TempPackWearEquipReq()
        req.ParseFromString(data)

        rsp = TempPackWearEquipRsp()
        rsp.status = StatusCode.StatusCode_OK

        idx = req.index  # temp_pack_index 从1开始(见 TreasureBoxPickup)
        if idx < 1 or idx > len(session.temp_pack):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.TempPackWearEquipRsp, rsp, packet_id)
            return

        chr_b = db.get_characters(session.player_id, req.char_id)
        if not chr_b:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.TempPackWearEquipRsp, rsp, packet_id)
            return
        chr = Character()
        chr.ParseFromString(chr_b[0])
        preset = chr.equipment_presets[0]  # 装备套装方案目前仅0可用

        instance_id, blob = session.temp_pack[idx - 1]
        item = ItemDetail()
        item.ParseFromString(blob)

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        tag = item.main_item.item_tag
        if tag == EBagItemTag.EBagItemTag_Weapon:
            # 卸下旧武器
            if preset.weapon:
                old_b = db.get_item_detail(session.player_id, None, preset.weapon)
                if old_b:
                    old = ItemDetail()
                    old.ParseFromString(old_b)
                    old.main_item.weapon.wearer_id = 0
                    db.set_item_detail(
                        session.player_id, old.SerializeToString(), None, preset.weapon
                    )
                    rsp1.items.add().CopyFrom(old)
            item.main_item.weapon.wearer_id = req.char_id
            preset.weapon = instance_id
            # 在队伍中则同步场景内武器展示(参考 CharacterEquipUpdate)
            team = db.get_players_info(session.player_id, "team")
            if team and req.char_id in team[0]:
                session.scene_player.team.char1.weapon_id = item.main_item.item_id
                sy = ServerSceneSyncDataNotice()
                sy.status = StatusCode.StatusCode_OK
                sy_data = sy.data.add()
                sy_data.player_id = session.player_id
                tmp = sy_data.server_data.add()
                tmp.action_type = SceneActionType.SceneActionType_UPDATE_EQUIP
                tmp.player.CopyFrom(session.scene_player)
                up_scene_action(session.scene_id, session.channel_id, sy)
        elif tag == EBagItemTag.EBagItemTag_Armor:
            item.main_item.armor.wearer_id = req.char_id
            # 部位取 Armor.armor.new_equip_type(0头/1胸/2手/3鞋, 与 EEquipType 对应)
            equip_type = 0
            for armor_cfg in res["Armor"]["armor"]["datas"]:
                if armor_cfg["item_i_d"] == item.main_item.item_id:
                    equip_type = armor_cfg.get("new_equip_type", 0)
                    break
            slot = None
            for armor_info in preset.armors:
                if armor_info.equip_type == equip_type:
                    slot = armor_info
                    break
            if slot is None:
                slot = preset.armors.add()
                slot.equip_type = equip_type
            # 卸下同部位旧防具
            if slot.armor_id:
                old_b = db.get_item_detail(session.player_id, None, slot.armor_id)
                if old_b:
                    old = ItemDetail()
                    old.ParseFromString(old_b)
                    old.main_item.armor.wearer_id = 0
                    db.set_item_detail(
                        session.player_id, old.SerializeToString(), None, slot.armor_id
                    )
                    rsp1.items.add().CopyFrom(old)
            slot.armor_id = instance_id
        else:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.TempPackWearEquipRsp, rsp, packet_id)
            return

        # 穿戴后离开临时背包, 转正到背包
        item.pack_type = ItemDetail.PackType.PackType_Inventory
        item.main_item.temp_pack_index = 0
        db.set_item_detail(
            session.player_id, item.SerializeToString(), None, instance_id
        )
        rsp1.items.add().CopyFrom(item)
        db.set_character(session.player_id, req.char_id, chr.SerializeToString())

        del session.temp_pack[idx - 1]
        rsp.temp_pack.max_size = Config.TEMP_PACK_MAX
        new_pack = []
        for i, (iid, blob2) in enumerate(session.temp_pack):
            tmp_item = ItemDetail()
            tmp_item.ParseFromString(blob2)
            tmp_item.main_item.temp_pack_index = i + 1
            new_pack.append((iid, tmp_item.SerializeToString()))
            rsp.temp_pack.item_infos.add().CopyFrom(tmp_item.main_item)
        session.temp_pack[:] = new_pack

        session.send(MsgId.TempPackWearEquipRsp, rsp, packet_id)  # 1413,1414
        session.send(MsgId.PackNotice, rsp1, 0)
