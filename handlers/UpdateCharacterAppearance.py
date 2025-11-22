from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as UpdateCharacterAppearanceReq_pb2
import proto.OverField_pb2 as UpdateCharacterAppearanceRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.UpdateCharacterAppearanceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # 解析请求数据
        req = UpdateCharacterAppearanceReq_pb2.UpdateCharacterAppearanceReq()
        req.ParseFromString(data)

        # 获取角色ID
        char_id = req.char_id
        logger.info(f"Handling appearance update for character {char_id}")

        # 从数据库获取该玩家对应角色id数据
        characters = db.get_characters(session.player_id, char_id)
        if not characters:
            logger.error(
                f"No character found for player {session.player_id} with character id {char_id}"
            )
            # 构建错误响应
            rsp = UpdateCharacterAppearanceRsp_pb2.UpdateCharacterAppearanceRsp()
            rsp.status = StatusCode_pb2.StatusCode_Error
            session.send(CmdId.UpdateCharacterAppearanceRsp, rsp, False, packet_id)
            return

        # 解析角色数据
        character = pb.Character()
        character.ParseFromString(characters[0])

        # 修改请求的数据（更新角色外观）
        character.character_appearance.badge = req.appearance.badge
        character.character_appearance.umbrella_id = req.appearance.umbrella_id
        character.character_appearance.insect_net_instance_id = (
            req.appearance.insect_net_instance_id
        )
        character.character_appearance.logging_axe_instance_id = (
            req.appearance.logging_axe_instance_id
        )
        character.character_appearance.water_bottle_instance_id = (
            req.appearance.water_bottle_instance_id
        )
        character.character_appearance.mining_hammer_instance_id = (
            req.appearance.mining_hammer_instance_id
        )
        character.character_appearance.collection_gloves_instance_id = (
            req.appearance.collection_gloves_instance_id
        )
        character.character_appearance.fishing_rod_instance_id = (
            req.appearance.fishing_rod_instance_id
        )

        # 保存更新后的角色数据到数据库
        db.up_character(session.player_id, char_id, character.SerializeToString())
        logger.info(f"Updated character {char_id} appearance")

        # 构建响应
        rsp = UpdateCharacterAppearanceRsp_pb2.UpdateCharacterAppearanceRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.char_id = char_id

        # 将更新后的外观数据添加到响应中
        rsp.appearance.badge = character.character_appearance.badge
        rsp.appearance.umbrella_id = character.character_appearance.umbrella_id
        rsp.appearance.insect_net_instance_id = (
            character.character_appearance.insect_net_instance_id
        )
        rsp.appearance.logging_axe_instance_id = (
            character.character_appearance.logging_axe_instance_id
        )
        rsp.appearance.water_bottle_instance_id = (
            character.character_appearance.water_bottle_instance_id
        )
        rsp.appearance.mining_hammer_instance_id = (
            character.character_appearance.mining_hammer_instance_id
        )
        rsp.appearance.collection_gloves_instance_id = (
            character.character_appearance.collection_gloves_instance_id
        )
        rsp.appearance.fishing_rod_instance_id = (
            character.character_appearance.fishing_rod_instance_id
        )

        session.send(CmdId.UpdateCharacterAppearanceRsp, rsp, False, packet_id)
        logger.info(f"Successfully handled appearance update for character {char_id}")
