from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPTeamRenameReq,
    MPTeamRenameRsp,
    MPTeamRenameNotice,
    StatusCode,
)

import server.mp_team as mp_team


@packet_handler(MsgId.MPTeamRenameReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamRenameReq()
        req.ParseFromString(data)

        rsp = MPTeamRenameRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.new_name = req.new_name

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
            elif team["leader"] != session.player_id:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NOT_LEADER
            elif not req.new_name:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NAME_EMPTY
            elif len(req.new_name) > 30:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NAME_TOO_LONG
            elif req.new_name == team["team_name"]:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NAME_UNCHANGED
            else:
                team["team_name"] = req.new_name
                rsp.team_id = team["team_id"]

                # 通知其他成员队名变更
                notice = MPTeamRenameNotice()
                notice.status = StatusCode.StatusCode_OK
                notice.team_id = team["team_id"]
                notice.team_name = req.new_name
                mp_team.broadcast(
                    team, MsgId.MPTeamRenameNotice, notice, exclude=session.player_id
                )  # 2460

        session.send(MsgId.MPTeamRenameRsp, rsp, packet_id)  # 2441,2442 队伍改名
