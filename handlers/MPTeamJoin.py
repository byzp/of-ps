from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import MPTeamJoinReq, MPTeamJoinRsp, StatusCode

import server.mp_team as mp_team


@packet_handler(MsgId.MPTeamJoinReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamJoinReq()
        req.ParseFromString(data)

        rsp = MPTeamJoinRsp()

        with mp_team.lock:
            team, status = mp_team.join_team(
                req.team_id, session.player_id, req.character_id
            )
            rsp.status = status
            if team is not None:
                mp_team.fill_team_detail(team, rsp.team_detail)
                # 通知原有成员有人入队(自己从 rsp 拿完整信息)
                mp_team.notify_members(team, exclude=session.player_id)  # 2458

        session.send(MsgId.MPTeamJoinRsp, rsp, packet_id)  # 2445,2446 加入队伍
