from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import json

from proto.net_pb2 import (
    CharacterStarUpReq,
    CharacterStarUpRsp,
    StatusCode,
    PackNotice,
    Character,
    ItemDetail,
)

import utils.db as db
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(MsgId.CharacterStarUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterStarUpReq()
        req.ParseFromString(data)

        rsp = CharacterStarUpRsp()

        character_data = db.get_characters(session.player_id, req.char_id)
        if not character_data:
            rsp.status = StatusCode.StatusCode_CHARACTER_NOT_FOUND
            session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)
            return

        character = Character()
        character.ParseFromString(character_data[0])

        current_star = character.star

        character_star_config = (
            res.get("Character", {}).get("character_star", {}).get("datas", [])
        )
        char_star_data = None
        for data in character_star_config:
            if data["i_d"] == req.char_id:
                char_star_data = data
                break

        if not char_star_data:
            rsp.status = StatusCode.StatusCode_CHARACTER_STAR_CONFIG_NOT_FOUND
            session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)
            return

        next_star = current_star + 1
        star_config = None
        for star_info in char_star_data["star_info"]:
            if star_info["star"] == next_star:
                star_config = star_info
                break

        if not star_config:
            rsp.status = StatusCode.StatusCode_CHARACTER_STAR_MAX_LEVEL
            session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)
            return

        item_id = star_config.get("item_i_d", 0)
        item_num = star_config.get("item_num", 0)

        if item_id == 0 or item_num == 0:
            rsp.status = StatusCode.StatusCode_CHARACTER_STAR_CONFIG_ERROR
            session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)
            return

        # 检查玩家是否有足够物品
        item_data = db.get_item_detail(session.player_id, item_id)
        if not item_data:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)
            return

        item = ItemDetail()
        item.ParseFromString(item_data)
        current_item_num = item.main_item.base_item.num

        if current_item_num < item_num:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)
            return

        character.star = next_star

        db.set_character(session.player_id, req.char_id, character.SerializeToString())

        # 扣除物品
        item.main_item.base_item.num -= item_num
        db.set_item_detail(session.player_id, item.SerializeToString(), item_id, None)

        # TODO 满星剩余碎片转换物品响应

        rsp.status = StatusCode.StatusCode_OK
        rsp.char_id = req.char_id
        rsp.star = character.star

        session.send(MsgId.CharacterStarUpRsp, rsp, packet_id)  # 角色升星 1037 1038

        # 更新碎片数量通知
        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.items.add().CopyFrom(item)
        session.send(MsgId.PackNotice, notice, packet_id)
