import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import BossRushStartBattleReq, BossRushStartBattleRsp, StatusCode
from server import boss_rush
import utils.db as db


@packet_handler(MsgId.BossRushStartBattleReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushStartBattleReq()
        req.ParseFromString(data)
        rsp = BossRushStartBattleRsp(season_id=req.season_id)
        season_data = boss_rush.season(req.season_id)
        if season_data is None or not boss_rush.season_active(season_data):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.BossRushStartBattleRsp, rsp, packet_id)
            return

        with boss_rush.lock, db.transaction():
            info, run, dirty = boss_rush.load_state(session.player_id, season_data)
            if dirty:
                boss_rush.save_state(session.player_id, req.season_id, info, run)
            if (
                not boss_rush.run_active(run)
                or run.get("stage_index") != info.current_stage_index
                or not 0 <= info.current_stage_index < len(info.stage_infos)
            ):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushStartBattleRsp, rsp, packet_id)
                return
            if run.get("status") == "battle":
                # 重试同一请求返回首次开局时间，不刷新战斗时限。
                rsp.status = StatusCode.StatusCode_OK
                rsp.stage_index = info.current_stage_index
                rsp.battle_start_time = int(run.get("battle_start_ms", 0) or 0)
                session.send(MsgId.BossRushStartBattleRsp, rsp, packet_id)
                return
            dungeon = boss_rush.dungeon_config(season_data, info.current_stage_index)
            if (
                run.get("status") != "entered"
                or not run.get("team")
                or not info.stage_infos[info.current_stage_index].teams
                or dungeon is None
            ):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushStartBattleRsp, rsp, packet_id)
                return
            fight_time = int(dungeon.get("fight_time", 0) or 0)
            if fight_time <= 0:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.BossRushStartBattleRsp, rsp, packet_id)
                return
            now_ms = int(time.time() * 1000)
            end_ms = int(run.get("end_time_ms", 0) or 0)
            battle_end_ms = min(end_ms, now_ms + fight_time * 1000)
            if battle_end_ms <= now_ms:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushStartBattleRsp, rsp, packet_id)
                return
            run["status"] = "battle"
            run["battle_start_ms"] = now_ms
            run["battle_end_ms"] = battle_end_ms
            boss_rush.save_state(session.player_id, req.season_id, info, run)
            # 保留旧键用于兼容旧客户端/运维检查；run 记录才是结算依据。
            db.set_kv(session.player_id, "boss_rush", f"{req.season_id}:battle_start", now_ms)

        rsp.status = StatusCode.StatusCode_OK
        rsp.stage_index = info.current_stage_index
        rsp.battle_start_time = now_ms
        session.send(MsgId.BossRushStartBattleRsp, rsp, packet_id)
