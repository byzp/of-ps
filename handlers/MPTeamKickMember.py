from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPTeamKickMemberReq,
    MPTeamKickMemberRsp,
    MPTeamPlayerKickedNotice,
    StatusCode,
)

import server.mp_team as mp_team


@packet_handler(MsgId.MPTeamKickMemberReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamKickMemberReq()
        req.ParseFromString(data)

        rsp = MPTeamKickMemberRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.target_id = req.target_id

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
            elif team["leader"] != session.player_id:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NOT_LEADER
            elif req.target_id not in team["members"]:
                rsp.status = StatusCode.StatusCode_PLAYER_NOT_IN_MP_TEAM
            elif req.target_id == session.player_id:
                rsp.status = StatusCode.StatusCode_BAD_REQ  # 不能踢自己
            else:
                team_id = team["team_id"]
                team, _ = mp_team.remove_member(req.target_id)

                # 通知被踢玩家
                kicked = MPTeamPlayerKickedNotice()
                kicked.status = StatusCode.StatusCode_OK
                kicked.team_id = team_id
                mp_team.send_to_players(
                    [req.target_id], MsgId.MPTeamPlayerKickedNotice, kicked
                )  # 2455

                # 通知剩余成员
                if team is not None:
                    mp_team.notify_members(team)  # 2458

        session.send(MsgId.MPTeamKickMemberRsp, rsp, packet_id)  # 2449,2450 踢出成员
