from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import CharacterLevelBreakReq, CharacterLevelBreakRsp, StatusCode, PackNotice

from server import character_growth as growth
from utils import achieve_track


# 角色突破：按 top_level/top_max_level 匹配配置，材料与等级上限同事务提交。
@packet_handler(MsgId.CharacterLevelBreakReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelBreakReq()
        req.ParseFromString(data)
        rsp = CharacterLevelBreakRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                character = growth.load_character(session.player_id, req.char_id)
                next_max_level, costs = growth.break_stage(character)
                if not growth.consume(session.player_id, costs, notice):
                    raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                character.max_level = next_max_level
                growth.save_character(session.player_id, character)
                rsp.char_id = req.char_id
                rsp.level = character.level
                rsp.exp = character.exp
                rsp.max_level = character.max_level
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
            return

        session.send(MsgId.CharacterLevelBreakRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        with achieve_track.batch(session):
            achieve_track.report(session, "character_break", match=req.char_id)
