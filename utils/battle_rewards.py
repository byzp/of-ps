"""战斗结算角色经验；曲线取资源，奖励量由可证实的战斗配置提供。"""

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import Character, TeamCharExpUpdateNotice, StatusCode
import utils.db as db
from utils import achieve_track
from utils.res_loader import res


def grant_character_exp(session, kind, battle_id):
    amount = Config.BATTLE_CHARACTER_EXP.get((kind, battle_id), 0)
    if not amount:
        return
    team = db.get_players_info(session.player_id, "team")[0]
    curve = {
        row["character_id"]: row["exp"]
        for row in res["Character"]["level"]["datas"][0]["level_info"]
    }
    notice = TeamCharExpUpdateNotice(status=StatusCode.StatusCode_OK)
    with achieve_track.batch(session):
        for character_id in dict.fromkeys(team):
            if not character_id:
                continue
            blob = db.get_characters(session.player_id, character_id)
            if not blob:
                continue
            character = Character()
            character.ParseFromString(blob[0])
            character.exp += amount
            previous_level = character.level
            while character.level < character.max_level:
                need = curve.get(character.level)
                if need is None or character.exp < need:
                    break
                character.exp -= need
                character.level += 1
            if character.level >= character.max_level:
                character.exp = 0
            db.set_character(
                session.player_id, character_id, character.SerializeToString()
            )
            notice.char_levels.add(
                character_id=character_id, level=character.level, exp=character.exp
            )
            if character.level != previous_level:
                achieve_track.report(
                    session,
                    "character_level",
                    match=character_id,
                    level=character.level,
                )
                achieve_track.character_level_count(session)
                if achieve_track.captain_id(session.player_id) == character_id:
                    achieve_track.captain_level(session, character.level)
                for field in ("char1", "char2", "char3"):
                    member = getattr(session.scene_player.team, field)
                    if member.char_id == character_id:
                        member.char_lv = character.level
        if notice.char_levels:
            session.send(MsgId.TeamCharExpUpdateNotice, notice, 0)
