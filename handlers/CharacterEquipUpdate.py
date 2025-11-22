from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CharacterEquipUpdateReq_pb2
import proto.OverField_pb2 as CharacterEquipUpdateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.CharacterEquipUpdateReq)
class Handler(PacketHandler):
    def _process_equipment_item(
        self, items, item_tag, instance_id, char_id, is_new_item=True
    ):
        """处理单个装备项"""
        for item_data in items:
            item = pb.ItemDetail()
            item.ParseFromString(item_data)

            # 检查物品标签和实例ID是否匹配
            if (
                item.main_item.item_tag == item_tag
                and self._get_instance_id(item, item_tag) == instance_id
            ):
                # 设置wearer_id
                wearer_id = char_id if is_new_item else 0
                self._set_wearer_id(item, item_tag, wearer_id)

                logger.info(
                    f"{'Setting' if is_new_item else 'Removing'} item instance {instance_id} wearer_id to {wearer_id}"
                )

                # 更新装备
                item_id = item.main_item.item_id
                db.set_item_detail(
                    self.session.player_id, item.SerializeToString(), item_id, None
                )
                return item
        return None

    def _get_instance_id(self, item, item_tag):
        """根据物品标签获取实例ID"""
        if item_tag == pb.EBagItemTag_Weapon:
            return item.main_item.weapon.instance_id
        elif item_tag == pb.EBagItemTag_Armor:
            return item.main_item.armor.instance_id
        elif item_tag == pb.EBagItemTag_Poster:
            return item.main_item.poster.instance_id
        return None

    def _set_wearer_id(self, item, item_tag, wearer_id):
        """根据物品标签设置wearer_id"""
        if item_tag == pb.EBagItemTag_Weapon:
            item.main_item.weapon.wearer_id = wearer_id
        elif item_tag == pb.EBagItemTag_Armor:
            item.main_item.armor.wearer_id = wearer_id
        elif item_tag == pb.EBagItemTag_Poster:
            item.main_item.poster.wearer_id = wearer_id

    def handle(self, session, data: bytes, packet_id: int):
        self.session = session
        req = CharacterEquipUpdateReq_pb2.CharacterEquipUpdateReq()
        req.ParseFromString(data)

        # 获取请求参数
        char_id = req.char_id
        preset_index = 0  # 固定为0
        weapon_instance_id = req.equipment_preset.weapon  # 这是武器的instance_id

        logger.info(
            f"Handling equipment update for character {char_id} with weapon instance {weapon_instance_id}"
        )

        # 获取角色数据
        characters = db.get_characters(session.player_id, char_id)
        if not characters:
            logger.error(
                f"No character found for player {session.player_id} with character id {char_id}"
            )
            # 构建错误响应
            rsp = CharacterEquipUpdateRsp_pb2.CharacterEquipUpdateRsp()
            rsp.status = StatusCode_pb2.StatusCode_Error
            session.send(CmdId.CharacterEquipUpdateRsp, rsp, False, packet_id)
            return

        character = pb.Character()
        character.ParseFromString(characters[0])

        # 更新角色装备预设，保存旧的装备实例ID
        old_weapon_instance_id = None
        old_armor_instance_ids = {}  # 保存旧的护甲实例ID，按装备类型分类
        old_poster_instance_ids = {}  # 保存旧的海报实例ID，按索引分类
        preset_found = False
        for preset in character.equipment_presets:
            if preset.preset_index == preset_index:
                old_weapon_instance_id = preset.weapon

                # 保存旧的防具实例ID
                for armor_info in preset.armors:
                    old_armor_instance_ids[armor_info.equip_type] = armor_info.armor_id

                # 保存旧的映像实例ID
                for poster_info in preset.posters:
                    old_poster_instance_ids[poster_info.poster_index] = (
                        poster_info.poster_id
                    )

                preset.CopyFrom(req.equipment_preset)
                preset_found = True
                break

        # 如果没找到对应的预设，添加新的预设
        if not preset_found:
            new_preset = character.equipment_presets.add()
            new_preset.CopyFrom(req.equipment_preset)

        # 保存更新后的角色数据
        db.set_character(session.player_id, char_id, character.SerializeToString())
        logger.info(f"Updated character {char_id} equipment preset {preset_index}")

        # 获取所有物品数据
        items = db.get_item_detail(session.player_id)

        # 处理旧装备：将原先角色装备的物品wearer_id修改为0
        old_items = []

        # 处理旧武器
        if old_weapon_instance_id:
            old_item = self._process_equipment_item(
                items, pb.EBagItemTag_Weapon, old_weapon_instance_id, char_id, False
            )
            if old_item:
                old_items.append(old_item)

        # 处理旧防具
        for equip_type, armor_id in old_armor_instance_ids.items():
            old_item = self._process_equipment_item(
                items, pb.EBagItemTag_Armor, armor_id, char_id, False
            )
            if old_item:
                old_items.append(old_item)

        # 处理旧映像
        for poster_index, poster_id in old_poster_instance_ids.items():
            old_item = self._process_equipment_item(
                items, pb.EBagItemTag_Poster, poster_id, char_id, False
            )
            if old_item:
                old_items.append(old_item)

        # 处理新装备：找到并设置新的装备
        target_items = []

        # 处理新武器
        if weapon_instance_id:
            new_item = self._process_equipment_item(
                items, pb.EBagItemTag_Weapon, weapon_instance_id, char_id, True
            )
            if new_item:
                target_items.append(new_item)

        # 处理新防具
        for armor_info in req.equipment_preset.armors:
            new_item = self._process_equipment_item(
                items, pb.EBagItemTag_Armor, armor_info.armor_id, char_id, True
            )
            if new_item:
                target_items.append(new_item)

        # 处理新映像
        for poster_info in req.equipment_preset.posters:
            new_item = self._process_equipment_item(
                items, pb.EBagItemTag_Poster, poster_info.poster_id, char_id, True
            )
            if new_item:
                target_items.append(new_item)

        # 构建响应
        rsp = CharacterEquipUpdateRsp_pb2.CharacterEquipUpdateRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # 添加角色数据
        characters = db.get_characters(session.player_id)
        for character_data in characters:
            character = pb.Character()
            character.ParseFromString(character_data)
            rsp.character.add().CopyFrom(character)

        # 添加物品通知（包括旧装备和新装备）
        for old_item in old_items:
            rsp.items.add().CopyFrom(old_item)

        for target_item in target_items:
            rsp.items.add().CopyFrom(target_item)

        session.send(CmdId.CharacterEquipUpdateRsp, rsp, False, packet_id)
        logger.info(f"Successfully handled equipment update for character {char_id}")
