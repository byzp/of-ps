from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    CharacterSkillLevelUpReq,
    CharacterSkillLevelUpRsp,
    CharacterSkill,
    ItemDetail,
    PackNotice,
    StatusCode,
)
import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils import achieve_track


def _get_skill_level(player_id, char_id, skill_id) -> int:
    raw = db.get_kv(player_id, "skills", f"{char_id}:{skill_id}", b"")
    return int(raw) if raw else 1


@packet_handler(MsgId.CharacterSkillLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterSkillLevelUpReq()
        rsp = CharacterSkillLevelUpRsp()
        req.ParseFromString(data)

        rsp.status = StatusCode.StatusCode_OK
        rsp.char_id = req.char_id

        # 角色需已拥有
        if not db.get_characters(session.player_id, req.char_id):
            rsp.status = StatusCode.StatusCode_CharNotExist
            session.send(MsgId.CharacterSkillLevelUpRsp, rsp, packet_id)
            return

        cur_level = _get_skill_level(session.player_id, req.char_id, req.skill_id)

        # 升级消耗: Spell.spell_level_up_info,
        # 各等级同价(表无逐级价格), 缺表则免费
        cost_list = []
        if (
            "Spell" in res
            and "spell_level_up_info" in res["Spell"]
            and "datas" in res["Spell"]["spell_level_up_info"]
            and res["Spell"]["spell_level_up_info"]["datas"]
            and res["Spell"]["spell_level_up_info"]["datas"][0].get(
                "spell_level_up_info_item"
            )
        ):
            entry = res["Spell"]["spell_level_up_info"]["datas"][0]
            it = entry["spell_level_up_info_item"][0]
            cost_list = list(zip(it.get("item_i_d", ()), it.get("num", ())))

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        if cost_list and not item_mgr.consume_items(
            session.player_id, cost_list, pack_notice=rsp1, session=session
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.CharacterSkillLevelUpRsp, rsp, packet_id)
            return

        new_level = cur_level + 1
        db.set_kv(
            session.player_id,
            "skills",
            f"{req.char_id}:{req.skill_id}",
            str(new_level).encode(),
        )

        rsp.skill.skill_id = req.skill_id
        rsp.skill.skill_level = new_level

        session.send(
            MsgId.CharacterSkillLevelUpRsp, rsp, packet_id
        )  # 角色技能升级 1035 1036
        # 成就: 升级角色技能(必杀技一并计入, 服务端无技能类别字段; 事件层归族)
        achieve_track.report(session, "skill_up")
        if rsp1.items:
            session.send(MsgId.PackNotice, rsp1, 0)
