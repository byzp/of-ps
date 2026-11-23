from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import MPTeamInfoReq, MPTeamInfoRsp, StatusCode

import server.mp_team as mp_team


@packet_handler(MsgId.MPTeamInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamInfoReq()
        req.ParseFromString(data)

        rsp = MPTeamInfoRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            # team_id 为 0 时查询自己所在队伍
            if req.team_id:
                team = mp_team.get_team(req.team_id)
            else:
                team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                if req.team_id:
                    rsp.status = StatusCode.StatusCode_MP_TEAM_NOT_EXIST
                else:
                    rsp.status = StatusCode.StatusCode_BAD_REQ
            else:
                mp_team.fill_team_detail(team, rsp.team_detail)

        session.send(MsgId.MPTeamInfoRsp, rsp, packet_id)  # 2422,2423 查询队伍信息
