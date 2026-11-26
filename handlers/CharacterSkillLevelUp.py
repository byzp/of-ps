from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import (
    CharacterSkillLevelUpReq,
    CharacterSkillLevelUpRsp,
    PackNotice,
    StatusCode,
)

from server import character_growth as growth
from utils import achieve_track


@packet_handler(MsgId.CharacterSkillLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterSkillLevelUpReq()
        req.ParseFromString(data)
        rsp = CharacterSkillLevelUpRsp(char_id=req.char_id, status=StatusCode.StatusCode_OK)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                character = growth.load_character(session.player_id, req.char_id)
                skill = next(
                    (item for item in character.character_skill_list if item.skill_id == req.skill_id),
                    None,
                )
                if skill is None:
                    raise growth.GrowthError(StatusCode.StatusCode_BAD_REQ)
                costs, next_level = growth.skill_upgrade(req.skill_id, skill.skill_level)
                if not growth.consume(session.player_id, costs, pack):
                    raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                skill.skill_level = next_level
                growth.save_character(session.player_id, character)
                rsp.skill.CopyFrom(skill)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.CharacterSkillLevelUpRsp, rsp, packet_id)
            return

        session.send(MsgId.CharacterSkillLevelUpRsp, rsp, packet_id)
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
        achieve_track.report(session, "skill_up")
