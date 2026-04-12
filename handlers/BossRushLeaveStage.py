from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BossRushLeaveStageReq,
    BossRushLeaveStageRsp,
    BossRushInfo,
    StatusCode,
)

from utils import db
from utils.res_loader import res
import time


@packet_handler(MsgId.BossRushLeaveStageReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushLeaveStageReq()
        req.ParseFromString(data)

        rsp = BossRushLeaveStageRsp()
        rsp.status = StatusCode.StatusCode_OK

        info_blob = db.get_boss_rush_info(session.player_id, req.season_id)
        if not info_blob:
            rsp.stage_best_score = 0
            rsp.best_total_score = 0
            rsp.total_rank_ratio = 0
            session.send(MsgId.BossRushLeaveStageRsp, rsp, packet_id)
            return

        info = BossRushInfo()
        info.ParseFromString(info_blob)

        total_damage_hp = req.total_damage_hp
        win = req.win

        stage_index = info.current_stage_index
        if stage_index < 0 or stage_index >= len(info.stage_infos):
            stage_index = 0

        stage_info = info.stage_infos[stage_index]

        # 获取当前关卡的目标血量
        max_hp = 0
        for stage in res["BossRush"]["boss_rush_stage"]["datas"]:
            if stage["i_d"] == info.season_id:
                stage_group = stage["boss_rush_stage_group_info"]
                if stage_index < len(stage_group):
                    max_hp = stage_group[stage_index].get("max_h_p", 0)
                break

        # 耗时
        total_consume_time = 0
        if info.start_time > 0 and info.start_time < 1776000000000:
            total_consume_time = int(time.time() * 1000) - info.start_time

        # 更新最后一个team的数据
        if len(stage_info.teams) > 0:
            team = stage_info.teams[-1]
            team.total_damage_hp = total_damage_hp
            team.total_consume_time = total_consume_time
            if max_hp > 0 and team.total_damage_hp > max_hp:
                team.total_damage_hp = max_hp

        # 累加当前对局的分数和伤害（不超过最大值）
        stage_info.total_score += total_damage_hp
        stage_info.total_damage_hp += total_damage_hp
        if max_hp > 0 and stage_info.total_damage_hp > max_hp:
            stage_info.total_damage_hp = max_hp
        stage_info.total_consume_time += total_consume_time

        # 检查是否达到目标血量
        is_passed = False
        if max_hp > 0 and stage_info.total_damage_hp >= max_hp:
            stage_info.is_passed = True
            is_passed = True

        # 更新累计信息
        info.best_total_score = 0
        for si in info.stage_infos:
            info.best_total_score += si.best_score
        info.total_rank_ratio = 9985

        # 重置赛季时间
        from datetime import datetime

        season_data = None
        for s in res["BossRush"]["boss_rush_season"]["datas"]:
            if s["i_d"] == info.season_id:
                season_data = s
                break
        if season_data:
            start_dt = datetime.strptime(season_data["start_time"], "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(season_data["end_time"], "%Y-%m-%d %H:%M:%S")
            info.start_time = int(start_dt.timestamp() * 1000)
            info.end_time = int(end_dt.timestamp() * 1000)

        # 如果通过，触发结算
        if is_passed:
            info.challenge_end_time = 0
            info.current_stage_index = -1
            info.used_characters.clear()
            # 结算每个stage
            for si in info.stage_infos:
                if si.total_score > si.best_score:
                    si.best_score = si.total_score
                si.total_score = 0
                si.total_damage_hp = 0
                si.teams.clear()

            # 重新计算总最佳分数
            info.best_total_score = 0
            for si in info.stage_infos:
                info.best_total_score += si.best_score

        # 保存并序列化
        db.set_boss_rush_info(
            session.player_id, info.season_id, info.SerializeToString()
        )

        rsp.stage_best_score = stage_info.best_score
        rsp.best_total_score = info.best_total_score
        rsp.total_rank_ratio = info.total_rank_ratio

        session.send(MsgId.BossRushLeaveStageRsp, rsp, packet_id)
