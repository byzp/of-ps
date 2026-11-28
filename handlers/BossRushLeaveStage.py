import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import BossRushLeaveStageReq, BossRushLeaveStageRsp, StatusCode
from server import boss_rush
import utils.db as db


@packet_handler(MsgId.BossRushLeaveStageReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushLeaveStageReq()
        req.ParseFromString(data)
        rsp = BossRushLeaveStageRsp()
        season_data = boss_rush.season(req.season_id)
        if season_data is None or not boss_rush.season_active(season_data):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.BossRushLeaveStageRsp, rsp, packet_id)
            return

        with boss_rush.lock, db.transaction():
            info, run, dirty = boss_rush.load_state(session.player_id, season_data)
            if dirty:
                boss_rush.save_state(session.player_id, req.season_id, info, run)
            if (
                not boss_rush.run_active(run)
                or run.get("status") != "battle"
                or not 0 <= info.current_stage_index < len(info.stage_infos)
                or run.get("stage_index") != info.current_stage_index
            ):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushLeaveStageRsp, rsp, packet_id)
                return
            stage = boss_rush.stage_config(season_data, info.current_stage_index)
            damage = boss_rush.validate_battle_report(req, season_data, info.current_stage_index)
            if damage is None or stage is None:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushLeaveStageRsp, rsp, packet_id)
                return
            now_ms = int(time.time() * 1000)
            battle_start = int(run.get("battle_start_ms", 0) or 0)
            battle_end = int(run.get("battle_end_ms", 0) or 0)
            if not battle_start or not battle_end or now_ms > battle_end:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushLeaveStageRsp, rsp, packet_id)
                return

            stage_info = info.stage_infos[info.current_stage_index]
            max_hp = int(stage["max_h_p"])
            elapsed_ms = max(0, now_ms - battle_start)
            remaining = max(0, max_hp - int(stage_info.total_score))
            damage = min(damage, remaining)
            passed = remaining > 0 and damage >= remaining
            if bool(req.win) != passed:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushLeaveStageRsp, rsp, packet_id)
                return

            stage_info.total_score += damage
            stage_info.total_damage_hp += damage
            stage_info.total_consume_time += elapsed_ms
            run["damage"] += damage
            run["elapsed_ms"] += elapsed_ms
            if passed:
                stage_info.is_passed = True
                boss_rush.settle(info)
                run["status"] = "settled"
                run["settled_at_ms"] = now_ms
                stage_best_score = stage_info.best_score
            else:
                stage_best_score = stage_info.total_score
                # 失败后释放本阶段队伍名额，但仍禁止复用本次挑战已使用的角色。
                run["status"] = "active"
                run["team"] = []
                run["team_index"] = -1
                run["battle_start_ms"] = 0
                run["battle_end_ms"] = 0
            boss_rush.save_state(session.player_id, req.season_id, info, run)
            db.del_kv(session.player_id, "boss_rush", f"{req.season_id}:battle_start")

        rsp.status = StatusCode.StatusCode_OK
        rsp.stage_best_score = stage_best_score
        rsp.best_total_score = info.best_total_score
        rsp.total_rank_ratio = info.total_rank_ratio
        session.send(MsgId.BossRushLeaveStageRsp, rsp, packet_id)
