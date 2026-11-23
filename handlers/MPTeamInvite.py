from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPTeamInviteReq,
    MPTeamInviteRsp,
    MPTeamInviteNotice,
    StatusCode,
)

import server.mp_team as mp_team
from server.scene_data import get_session


@packet_handler(MsgId.MPTeamInviteReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamInviteReq()
        req.ParseFromString(data)

        rsp = MPTeamInviteRsp()
        rsp.status = StatusCode.StatusCode_OK

        notice = None
        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_INVITER_NOT_IN_TEAM
            elif mp_team.get_team_by_player(req.target_id) is not None:
                rsp.status = StatusCode.StatusCode_MP_INVITEE_IN_TEAM
            elif len(team["members"]) >= team["max_members"]:
                rsp.status = StatusCode.StatusCode_MP_TEAM_FULL
            else:
                notice = MPTeamInviteNotice()
                notice.status = StatusCode.StatusCode_OK
                notice.inviter = session.player_id
                mp_team.fill_team_base(team, notice.team_base)

        if notice is not None:
            # 向目标玩家推送邀请通知(跨服邀请依赖互联路由, 暂不开放)
            sent = False
            for s in get_session():
                if s.player_id == req.target_id:
                    s.send(MsgId.MPTeamInviteNotice, notice, 0)  # 2454
                    sent = True
                    break
            if not sent:
                rsp.status = StatusCode.StatusCode_FAIL  # 目标玩家不在线

        session.send(MsgId.MPTeamInviteRsp, rsp, packet_id)  # 2443,2444 邀请入队
