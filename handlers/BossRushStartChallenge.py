import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import BossRushStartChallengeReq, BossRushStartChallengeRsp, StatusCode
from server import boss_rush
import utils.db as db


@packet_handler(MsgId.BossRushStartChallengeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushStartChallengeReq()
        req.ParseFromString(data)
        rsp = BossRushStartChallengeRsp(season_id=req.season_id)
        season_data = boss_rush.season(req.season_id)
        if season_data is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
            return
        if not boss_rush.season_active(season_data):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
            return
        if not boss_rush.stage_unlocked(season_data, req.stage_index):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
            return
        dungeon = boss_rush.dungeon_config(season_data, req.stage_index)
        if not dungeon or boss_rush.monster_snapshot(season_data, req.stage_index) is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
            return
        level_row = db.get_players_info(session.player_id, "level")
        level = int(level_row[0] or 0) if level_row else 0
        if level < int(dungeon.get("need_player_level", 1) or 1):
            rsp.status = StatusCode.StatusCode_Lv_Not_Enough
            session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
            return
        battle_time = int(season_data.get("battle_time", 0) or 0)
        if battle_time <= 0:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
            return

        with boss_rush.lock, db.transaction():
            info, run, dirty = boss_rush.load_state(session.player_id, season_data)
            if boss_rush.run_active(run):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
                return
            now = int(time.time())
            now_ms = now * 1000
            season_end = boss_rush.parse_time(season_data.get("end_time"))
            end_time_ms = min(season_end, now_ms + battle_time * 1000)
            if end_time_ms <= now_ms:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
                return
            # 新挑战不继承上一轮尚未结算的临时队伍/伤害。
            boss_rush.settle(info)
            info.current_stage_index = req.stage_index
            info.challenge_end_time = end_time_ms // 1000
            run = boss_rush.new_run(req.season_id, req.stage_index, now_ms, end_time_ms)
            boss_rush.save_state(session.player_id, req.season_id, info, run)

        rsp.status = StatusCode.StatusCode_OK
        rsp.stage_info.CopyFrom(info.stage_infos[req.stage_index])
        session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
