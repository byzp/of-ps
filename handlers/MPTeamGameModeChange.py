from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPTeamGameModeChangeReq,
    MPTeamGameModeChangeRsp,
    MPTeamGameModeChangeNotice,
    StatusCode,
)
from utils.res_loader import res

import server.mp_team as mp_team


@packet_handler(MsgId.MPTeamGameModeChangeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamGameModeChangeReq()
        req.ParseFromString(data)

        rsp = MPTeamGameModeChangeRsp()

        # 模式校验(同 MPTeamCreate)
        _modes = {
            m["i_d"]: m
            for m in res.get("TeamGameplay", {}).get("mode", {}).get("datas", [])
        }
        if _modes and req.mode_id not in _modes:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.MPTeamGameModeChangeRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
            elif team["leader"] != session.player_id:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NOT_LEADER
            elif (
                team["mode_id"] == req.mode_id
                and team["sub_mode_id"] == req.sub_mode_id
            ):
                rsp.status = StatusCode.StatusCode_MP_PLAY_INFO_UNCHANGED
            else:
                team["mode_id"] = req.mode_id
                team["sub_mode_id"] = req.sub_mode_id
                # 模式切换后所有成员准备状态重置
                for m in team["members"].values():
                    m["is_ready"] = False
                rsp.team_id = team["team_id"]
                mp_team.fill_mode_info(team, rsp.game_mode)

                # 通知其他成员模式变更
                notice = MPTeamGameModeChangeNotice()
                notice.status = StatusCode.StatusCode_OK
                notice.team_id = team["team_id"]
                mp_team.fill_mode_info(team, notice.game_mode)
                mp_team.broadcast(
                    team,
                    MsgId.MPTeamGameModeChangeNotice,
                    notice,
                    exclude=session.player_id,
                )  # 2421

        session.send(
            MsgId.MPTeamGameModeChangeRsp, rsp, packet_id
        )  # 2419,2420 切换游戏模式
