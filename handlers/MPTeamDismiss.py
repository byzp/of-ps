from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPTeamDismissReq,
    MPTeamDismissRsp,
    MPTeamDismissNotice,
    StatusCode,
)

import server.mp_team as mp_team


@packet_handler(MsgId.MPTeamDismissReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamDismissReq()
        req.ParseFromString(data)

        rsp = MPTeamDismissRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
            elif team["leader"] != session.player_id:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NOT_LEADER
            else:
                team_id = team["team_id"]
                member_ids = mp_team.dismiss_team(team_id)

                # 通知其他成员队伍已解散(队长自己走 rsp)
                notice = MPTeamDismissNotice()
                notice.status = StatusCode.StatusCode_OK
                notice.team_id = team_id
                member_ids = [i for i in member_ids if i != session.player_id]
                mp_team.send_to_players(
                    member_ids, MsgId.MPTeamDismissNotice, notice
                )  # 2453

        session.send(MsgId.MPTeamDismissRsp, rsp, packet_id)  # 2451,2452 解散队伍
