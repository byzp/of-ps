from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import BossRushEnterStageReq, BossRushEnterStageRsp, Character, StatusCode
from server import boss_rush
import utils.db as db


@packet_handler(MsgId.BossRushEnterStageReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushEnterStageReq()
        req.ParseFromString(data)
        rsp = BossRushEnterStageRsp(season_id=req.season_id)
        season_data = boss_rush.season(req.season_id)
        if season_data is None or not boss_rush.season_active(season_data):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
            return

        with boss_rush.lock, db.transaction():
            info, run, dirty = boss_rush.load_state(session.player_id, season_data)
            if dirty:
                boss_rush.save_state(session.player_id, req.season_id, info, run)
            if (
                not boss_rush.run_active(run)
                or run.get("stage_index") != info.current_stage_index
                or not 0 <= info.current_stage_index < len(info.stage_infos)
                or run.get("status") == "battle"
            ):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
                return
            dungeon = boss_rush.dungeon_config(season_data, info.current_stage_index)
            battle = boss_rush.battle_info(season_data, info.current_stage_index)
            if dungeon is None or battle is None:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
                return
            characters = list(dict.fromkeys(req.characters))
            if (
                not characters
                or any(character_id <= 0 for character_id in characters)
                or len(characters) > int(dungeon.get("use_character_max_number", 3) or 3)
            ):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
                return
            stage_info = info.stage_infos[info.current_stage_index]
            if run.get("status") == "entered":
                if list(run.get("team", ())) != characters:
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                    session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
                    return
            else:
                if len(stage_info.teams) >= boss_rush.max_attempts(dungeon):
                    rsp.status = StatusCode.StatusCode_DungeonTeamFull
                    session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
                    return
                if any(character_id in info.used_characters for character_id in characters):
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                    session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
                    return
                owned = set()
                for character_blob in db.get_characters(session.player_id):
                    character = Character()
                    character.ParseFromString(character_blob)
                    owned.add(character.character_id)
                if any(character_id not in owned for character_id in characters):
                    rsp.status = StatusCode.StatusCode_CharNotExist
                    session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
                    return
                team = stage_info.teams.add()
                team.characters.extend(characters)
                info.used_characters.extend(characters)
                run["team"] = characters
                run["team_index"] = len(stage_info.teams) - 1
                run["status"] = "entered"
                boss_rush.save_state(session.player_id, req.season_id, info, run)

        rsp.status = StatusCode.StatusCode_OK
        rsp.battle_info.CopyFrom(battle)
        session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
