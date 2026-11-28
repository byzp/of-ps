from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import CharacterLevelUpReq, CharacterLevelUpRsp, StatusCode, PackNotice

from server import character_growth as growth
from utils import achieve_track
import utils.db as db


# 角色升级。经验曲线按角色 growth_level_i_d 读取，材料与角色 Blob 同事务更新。
@packet_handler(MsgId.CharacterLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelUpReq()
        req.ParseFromString(data)
        rsp = CharacterLevelUpRsp(status=StatusCode.StatusCode_OK)
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        new_level = new_exp = 0
        try:
            with growth.transaction(session.player_id):
                character = growth.load_character(session.player_id, req.char_id)
                player_levels = db.get_players_info(session.player_id, "level")
                player_level = int(player_levels[0]) if player_levels else 1
                costs, new_level, new_exp = growth.plan_level_up(
                    character,
                    list(req.nums),
                    player_level,
                    Config.CHARACTER_LEVEL_UP_ENERGY_ITEMS,
                )
                if not growth.consume(session.player_id, costs, notice):
                    raise growth.GrowthError(StatusCode.StatusCode_ITEM_NOT_ENOUGH)
                character.level = new_level
                character.exp = new_exp
                growth.save_character(session.player_id, character)
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.CharacterLevelUpRsp, rsp, packet_id)
            return

        rsp.char_id = req.char_id
        rsp.level = new_level
        rsp.exp = new_exp
        session.send(MsgId.CharacterLevelUpRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
        with achieve_track.batch(session):
            achieve_track.report(
                session, "energy_drink", amount=sum(int(n or 0) for n in req.nums)
            )
            achieve_track.report(
                session, "character_level", match=req.char_id, level=new_level
            )
            achieve_track.character_level_count(session)
            if achieve_track.captain_id(session.player_id) == req.char_id:
                achieve_track.captain_level(session, new_level)
