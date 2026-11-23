from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    CharacterLevelBreakReq,
    CharacterLevelBreakRsp,
    StatusCode,
    PackNotice,
    Character,
)
import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils import achieve_track

"""
# 角色突破 1041 1042
rule_need_item 校验+扣除改走 item_mgr.consume_items 原子入口
(原逐件循环在第 2 件不足时已吞掉第 1 件且不回 1400, 属静默损失);
包序对齐官方成功样本: Rsp → 1400 → 1720/1764/1718(帧尾)。
"""


@packet_handler(MsgId.CharacterLevelBreakReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelBreakReq()

        rsp = CharacterLevelBreakRsp()
        req.ParseFromString(data)
        notice = PackNotice()
        notice.status = StatusCode.StatusCode_OK

        character_data = db.get_characters(session.player_id, req.char_id)
        if not character_data:
            rsp.status = StatusCode.StatusCode_CharNotExist
            rsp.char_id = req.char_id
            session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
            return

        character = Character()
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
            rsp.status = StatusCode.StatusCode_CharNotExist
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
            rsp.status = StatusCode.StatusCode_CharacterSkillLvIsMax
            rsp.char_id = req.char_id
            session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
            return

        # 整体校验后统一扣除(要么全扣要么零变更)
        cost_list = [
            (n["need_item_i_d"], n["need_item_count"])
            for n in level_config["rule_need_item"]
        ]
        with achieve_track.batch(session):
            if cost_list and not item_mgr.consume_items(
                session.player_id,
                cost_list,
                pack_notice=notice,
                session=session,
            ):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                rsp.char_id = req.char_id
                session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
                return

            character.max_level = next_max_level
            db.set_character(
                session.player_id, req.char_id, character.SerializeToString()
            )

            rsp.status = StatusCode.StatusCode_OK
            rsp.char_id = req.char_id
            rsp.level = character.level
            rsp.exp = character.exp
            rsp.max_level = character.max_level

            # 成就: 角色突破(分角色 + 总计, 事件层归族)
            achieve_track.report(session, "character_break", match=req.char_id)
            session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)  # 1041,1042
            if len(notice.items):
                session.send(MsgId.PackNotice, notice, 0)  # 1400
