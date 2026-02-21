from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
from proto.net_pb2 import (
    CharacterLevelBreakReq,
    CharacterLevelBreakRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(MsgId.CharacterLevelBreakReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelBreakReq()
        rsp = CharacterLevelBreakRsp()
        req.ParseFromString(data)

        character_data = db.get_characters(session.player_id, req.char_id)
        if not character_data:
            rsp.status = StatusCode.StatusCode_CHARACTER_NOT_FOUND
            rsp.char_id = req.char_id
            session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
            return

        character = CharacterLevelBreakReq.Character()
        character.ParseFromString(character_data[0])

        # 获取角色当前最大等级
        current_max_level = character.max_level

        # 获取角色突破配置
        character_config = (
            res.get("Character", {}).get("level_rule", {}).get("datas", [])
        )
        char_level_data = None
        for data in character_config:
            if data["i_d"] == req.char_id:
                char_level_data = data
                break

        if not char_level_data:
            rsp.status = StatusCode.StatusCode_CHAR_NOT_EXIST
            rsp.char_id = req.char_id
            session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
            return

        # 查找下一个突破阶段的配置
        next_max_level = min(current_max_level + 20, 100)
        level_config = None
        for level_info in char_level_data["level_rule_info"]:
            if level_info["top_max_level"] == next_max_level:
                level_config = level_info
                break

        if not level_config:
            rsp.status = StatusCode.StatusCode_CHARACTER_SKILL_LV_IS_MAX
            rsp.char_id = req.char_id
            session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
            return

        # 检查并扣除所需物品
        for need_item in level_config["rule_need_item"]:
            item_id = need_item["need_item_i_d"]
            item_count = need_item["need_item_count"]

            # 检查玩家是否有足够物品
            item_data = db.get_item_detail(session.player_id, item_id)
            if not item_data:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                rsp.char_id = req.char_id
                session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
                return

            # 解析物品数据
            item = CharacterLevelBreakReq.ItemDetail()
            item.ParseFromString(item_data)
            current_item_num = item.main_item.base_item.num

            # 检查物品数量是否足够
            if current_item_num < item_count:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                rsp.char_id = req.char_id
                session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
                return

            # 扣除物品
            item.main_item.base_item.num -= item_count
            db.set_item_detail(
                session.player_id, item.SerializeToString(), item_id, None
            )

            # 发送物品变动通知
            notice = PackNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.items.add().CopyFrom(item)
            session.send(MsgId.PackNotice, notice, packet_id)

        character.max_level = next_max_level
        db.set_character(session.player_id, req.char_id, character.SerializeToString())

        rsp.status = StatusCode.StatusCode_OK
        rsp.char_id = req.char_id
        rsp.level = character.level
        rsp.exp = character.exp
        rsp.max_level = character.max_level

        session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)  # 角色突破 1041 1042
