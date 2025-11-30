from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CharacterLevelUpReq_pb2
import proto.OverField_pb2 as CharacterLevelUpRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as PackNotice_pb2
import utils.db as db
import utils.res_loader as res_loader
from proto.OverField_pb2 import Character

logger = logging.getLogger(__name__)


@packet_handler(CmdId.CharacterLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelUpReq_pb2.CharacterLevelUpReq()
        req.ParseFromString(data)
        rsp = CharacterLevelUpRsp_pb2.CharacterLevelUpRsp()

        small_energy_bottle = req.nums[0] if len(req.nums) > 0 else 0
        medium_energy_bottle = req.nums[1] if len(req.nums) > 1 else 0
        large_energy_bottle = req.nums[2] if len(req.nums) > 2 else 0

        energy_items = [
            (190, small_energy_bottle),  # 小瓶能量饮料
            (191, medium_energy_bottle),  # 中瓶能量饮料
            (192, large_energy_bottle),  # 大瓶能量饮料
        ]

        for item_id, quantity in energy_items:
            if quantity > 0:
                item_data = db.get_item_detail(session.player_id, item_id)
                if item_data:
                    item = CharacterLevelUpReq_pb2.ItemDetail()
                    item.ParseFromString(item_data)
                    item.main_item.base_item.num = max(
                        0, item.main_item.base_item.num - quantity
                    )
                    db.set_item_detail(
                        session.player_id, item.SerializeToString(), item_id, None
                    )

        character_data_list = db.get_characters(session.player_id, req.char_id)
        if not character_data_list:
            rsp.status = StatusCode_pb2.StatusCode_CHARACTER_NOT_FOUND
            session.send(CmdId.CharacterLevelUpRsp, rsp, packet_id)
            return

        character = Character()
        character.ParseFromString(character_data_list[0])

        current_level = character.level
        current_exp = character.exp
        max_level = character.max_level

        total_exp = (
            small_energy_bottle * 1000
            + medium_energy_bottle * 5000
            + large_energy_bottle * 20000
        )

        level_configs = res_loader.res["Character"]["level"]["datas"][0]["level_info"]

        new_exp = current_exp + total_exp
        new_level = current_level

        for level_config in level_configs:
            if (
                level_config["level"] == new_level
                and new_exp >= level_config["need_exp"]
                and new_level < max_level
            ):
                new_level += 1
                new_exp -= level_config["need_exp"]
            elif level_config["level"] > new_level:
                break

        if new_level >= max_level:
            new_exp = 0
            new_level = max_level

        character.level = new_level
        character.exp = new_exp

        coin_cost = 0
        if current_level > 0 and current_level <= len(level_configs):
            for level_config in level_configs:
                if level_config["level"] == current_level:
                    coin_cost = int(total_exp * level_config["exp_to_coin"])
                    break
        if coin_cost > 0:
            coin_item_id = 101  # 金币ID
            coin_data = db.get_item_detail(session.player_id, coin_item_id)
            if coin_data:
                coin_item = CharacterLevelUpReq_pb2.ItemDetail()
                coin_item.ParseFromString(coin_data)
                coin_item.main_item.base_item.num = max(0, coin_item.main_item.base_item.num - coin_cost)
                db.set_item_detail(session.player_id, coin_item.SerializeToString(), coin_item_id, None)
                
                # 更新金币通知
                notice = PackNotice_pb2.PackNotice()
                notice.status = StatusCode_pb2.StatusCode_OK
                notice.items.add().CopyFrom(coin_item)
                session.send(CmdId.PackNotice, notice, packet_id)

        db.set_character(session.player_id, req.char_id, character.SerializeToString())

        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.char_id = req.char_id
        rsp.level = new_level
        rsp.exp = new_exp

        session.send(CmdId.CharacterLevelUpRsp, rsp, packet_id)  # 角色升级 1039 1040
