from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BossRushEnterStageReq,
    BossRushEnterStageRsp,
    BossRushInfo,
    BossRushStageBattleInfo,
    StatusCode,
)

from utils import db


@packet_handler(MsgId.BossRushEnterStageReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushEnterStageReq()
        req.ParseFromString(data)

        rsp = BossRushEnterStageRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.season_id = req.season_id

        # BossRushStartChallenge/开始->(BossRushEnterStage->BossRushStartBattle->BossRushLeaveStage)/多次分段小战斗->BossRushTerminateChallenge/结束

        # 保存队伍信息到BossRushInfo.stage_infos[stage_index].teams
        info_blob = db.get_boss_rush_info(session.player_id, req.season_id)
        if info_blob:
            info = BossRushInfo()
            info.ParseFromString(info_blob)

            # 根据current_stage_index确定当前关卡
            stage_index = info.current_stage_index
            if stage_index < 0 or stage_index >= len(info.stage_infos):
                stage_index = 0
                info.current_stage_index = 0

            # 获取对应的stage_info
            stage_info = info.stage_infos[stage_index]

            # 添加新的队伍信息
            team = stage_info.teams.add()
            team.characters.extend(req.characters)
            team.total_damage_hp = 0
            team.total_consume_time = 0

            # 累积记录角色
            for char_id in req.characters:
                if char_id not in info.used_characters:
                    info.used_characters.append(char_id)

            db.set_boss_rush_info(
                session.player_id, req.season_id, info.SerializeToString()
            )

        # 初始化空的battle_info
        battle_info = BossRushStageBattleInfo()
        rsp.battle_info.CopyFrom(battle_info)

        session.send(MsgId.BossRushEnterStageRsp, rsp, packet_id)
