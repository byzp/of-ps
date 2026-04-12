from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BossRushTerminateChallengeReq,
    BossRushTerminateChallengeRsp,
    BossRushInfo,
    StatusCode,
)

from utils import db


@packet_handler(MsgId.BossRushTerminateChallengeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushTerminateChallengeReq()
        req.ParseFromString(data)

        rsp = BossRushTerminateChallengeRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.season_id = req.season_id

        info_blob = db.get_boss_rush_info(session.player_id, req.season_id)
        if info_blob:
            info = BossRushInfo()
            info.ParseFromString(info_blob)
            info.challenge_end_time = 0
            info.current_stage_index = -1
            # 计算三个难度的最佳分数
            for si in info.stage_infos:
                if si.total_score > si.best_score:
                    si.best_score = si.total_score
                # 清空对局数据
                si.total_score = 0
                si.total_damage_hp = 0
                si.teams.clear()
            # 计算总最佳分数
            info.best_total_score = 0
            for si in info.stage_infos:
                info.best_total_score += si.best_score

            db.set_boss_rush_info(
                session.player_id, req.season_id, info.SerializeToString()
            )

        session.send(MsgId.BossRushTerminateChallengeRsp, rsp, packet_id)
