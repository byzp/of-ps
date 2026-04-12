from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BossRushInfoReq,
    BossRushInfoRsp,
    BossRushInfo,
    StatusCode,
)

from utils.res_loader import res
from utils import db
import time


@packet_handler(MsgId.BossRushInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushInfoReq()
        req.ParseFromString(data)

        rsp = BossRushInfoRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 处理 season_id 为 0 的情况
        season_id = req.season_id
        current_time = int(time.time())

        if season_id == 0:
            from datetime import datetime

            for s in res["BossRush"]["boss_rush_season"]["datas"]:
                start_dt = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S")
                if start_dt.timestamp() <= current_time <= end_dt.timestamp():
                    season_id = s["i_d"]
                    break
            if season_id == 0:
                all_seasons = res["BossRush"]["boss_rush_season"]["datas"]
                season_id = max(s["i_d"] for s in all_seasons)

        season_data = None
        for i in res["BossRush"]["boss_rush_season"]["datas"]:
            if i["i_d"] == season_id:
                season_data = i
                break

        if season_data:
            player_id = session.player_id
            from datetime import datetime

            start_dt = datetime.strptime(season_data["start_time"], "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(season_data["end_time"], "%Y-%m-%d %H:%M:%S")
            show_rank_dt = datetime.strptime(
                season_data["show_rank_time"], "%Y-%m-%d %H:%M:%S"
            )

            # 尝试从数据库加载已有的BossRushInfo
            stored_info_blob = db.get_boss_rush_info(player_id, season_id)
            if stored_info_blob:
                info = BossRushInfo()
                info.ParseFromString(stored_info_blob)

                # 检查挑战时间是否已结束
                if info.challenge_end_time > 0:
                    current_time_sec = int(time.time())
                    if current_time_sec >= info.challenge_end_time:
                        # 时间已到，自动结算
                        info.challenge_end_time = 0
                        info.current_stage_index = -1

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

                        db.set_boss_rush_info(
                            player_id, season_id, info.SerializeToString()
                        )

                rsp.info.CopyFrom(info)
            else:
                # 初始化空的BossRushInfo
                info = rsp.info
                info.season_id = season_id
                info.current_stage_index = -1
                info.start_time = int(start_dt.timestamp() * 1000)
                info.end_time = int(end_dt.timestamp() * 1000)
                info.show_rank_time = int(show_rank_dt.timestamp() * 1000)

                # 解析阶段信息（空占位）
                stage_group_data = None
                for stage in res["BossRush"]["boss_rush_stage"]["datas"]:
                    if stage["i_d"] == season_id:
                        stage_group_data = stage
                        break

                if stage_group_data:
                    for stage_index, stage_info_cfg in enumerate(
                        stage_group_data["boss_rush_stage_group_info"]
                    ):
                        stage_msg = info.stage_infos.add()
                        stage_msg.stage_index = stage_index
                db.set_boss_rush_info(player_id, season_id, info.SerializeToString())
        session.send(MsgId.BossRushInfoRsp, rsp, packet_id)
