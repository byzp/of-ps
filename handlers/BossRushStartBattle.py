from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import time

from proto.net_pb2 import (
    BossRushStartBattleReq,
    BossRushStartBattleRsp,
    BossRushInfo,
    StatusCode,
)

from utils import db


@packet_handler(MsgId.BossRushStartBattleReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushStartBattleReq()
        req.ParseFromString(data)

        rsp = BossRushStartBattleRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.season_id = req.season_id

        # 从 BossRushInfo 读取当前关卡索引, 与 EnterStage/LeaveStage 保持一致
        rsp.stage_index = 0
        info_blob = db.get_boss_rush_info(session.player_id, req.season_id)
        if info_blob:
            info = BossRushInfo()
            info.ParseFromString(info_blob)
            if info.current_stage_index >= 0:
                rsp.stage_index = info.current_stage_index

        # 记录战斗开始时间（用于LeaveStage计算耗时）
        battle_start_time = int(time.time() * 1000)
        rsp.battle_start_time = battle_start_time

        session.send(MsgId.BossRushStartBattleRsp, rsp, packet_id)
