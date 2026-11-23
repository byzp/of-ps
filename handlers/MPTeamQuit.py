from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import MPTeamQuitReq, MPTeamQuitRsp, StatusCode

import server.mp_team as mp_team


@packet_handler(MsgId.MPTeamQuitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamQuitReq()
        req.ParseFromString(data)

        rsp = MPTeamQuitRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
                session.send(MsgId.MPTeamQuitRsp, rsp, packet_id)  # 2447,2448
                return

            # 队长退出时自动把队长转移给最早入队的成员
            team, team_id = mp_team.remove_member(session.player_id)
            rsp.team_id = team_id
            if team is not None:
                # 通知剩余成员
                mp_team.notify_members(team)  # 2458

        session.send(MsgId.MPTeamQuitRsp, rsp, packet_id)  # 2447,2448 退出队伍
