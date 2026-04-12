from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import time
from datetime import datetime

from proto.net_pb2 import (
    BossRushStartChallengeReq,
    BossRushStartChallengeRsp,
    BossRushInfo,
    BossRushStageInfo,
    StatusCode,
)

from utils.res_loader import res
from utils import db


@packet_handler(MsgId.BossRushStartChallengeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushStartChallengeReq()
        req.ParseFromString(data)

        rsp = BossRushStartChallengeRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.season_id = req.season_id

        # 验证赛季是否存在
        season_data = None
        for i in res["BossRush"]["boss_rush_season"]["datas"]:
            if i["i_d"] == req.season_id:
                season_data = i
                break

        if season_data:
            player_id = session.player_id
            info_blob = db.get_boss_rush_info(player_id, req.season_id)
            if not info_blob:
                info = BossRushInfo()
                info.season_id = req.season_id
                info.current_stage_index = req.stage_index

                start_dt = datetime.strptime(
                    season_data["start_time"], "%Y-%m-%d %H:%M:%S"
                )
                end_dt = datetime.strptime(season_data["end_time"], "%Y-%m-%d %H:%M:%S")
                show_rank_dt = datetime.strptime(
                    season_data["show_rank_time"], "%Y-%m-%d %H:%M:%S"
                )

                info.start_time = int(start_dt.timestamp() * 1000)
                info.end_time = int(end_dt.timestamp() * 1000)
                info.show_rank_time = int(show_rank_dt.timestamp() * 1000)

                # 添加空的stage_infos占位
                stage_group_data = None
                for stage in res["BossRush"]["boss_rush_stage"]["datas"]:
                    if stage["i_d"] == req.season_id:
                        stage_group_data = stage
                        break

                if stage_group_data:
                    for stage_index, stage_info_cfg in enumerate(
                        stage_group_data["boss_rush_stage_group_info"]
                    ):
                        stage_msg = info.stage_infos.add()
                        stage_msg.stage_index = stage_index

                # 设置结束时间(3600秒)
                battle_time_limit = season_data.get("battle_time", 3600)
                info.challenge_end_time = int(time.time()) + battle_time_limit

                db.set_boss_rush_info(
                    player_id, req.season_id, info.SerializeToString()
                )
            else:
                # 已有记录，更新current_stage_index和挑战结束时间
                info = BossRushInfo()
                info.ParseFromString(info_blob)
                info.current_stage_index = req.stage_index
                battle_time_limit = season_data.get("battle_time", 3600)
                info.challenge_end_time = int(time.time()) + battle_time_limit
                db.set_boss_rush_info(
                    player_id, req.season_id, info.SerializeToString()
                )

            stage_info = BossRushStageInfo()
            stage_info.stage_index = req.stage_index
            rsp.stage_info.CopyFrom(stage_info)

        session.send(MsgId.BossRushStartChallengeRsp, rsp, packet_id)
