from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPBeaconPlayerReadyReq,
    MPBeaconPlayerReadyRsp,
    MPTeamBeaconNotice,
    MPBeaconCanStartNotice,
    StatusCode,
)

import server.mp_team as mp_team


@packet_handler(MsgId.MPBeaconPlayerReadyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPBeaconPlayerReadyReq()
        req.ParseFromString(data)

        rsp = MPBeaconPlayerReadyRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None or (req.team_id and team["team_id"] != req.team_id):
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
                session.send(MsgId.MPBeaconPlayerReadyRsp, rsp, packet_id)  # 2469,2470
                return

            old_can_start = mp_team.can_start(team)
            team["members"][session.player_id]["is_ready"] = req.is_ready
            new_can_start = mp_team.can_start(team)

            # 全队同步信标(含成员准备状态 map)
            notice = MPTeamBeaconNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.team_id = team["team_id"]
            mp_team.fill_beacon(team, notice.beacon)
            mp_team.broadcast(team, MsgId.MPTeamBeaconNotice, notice)  # 2418

            # can_start 变化时单独通知
            if new_can_start != old_can_start:
                cs = MPBeaconCanStartNotice()
                cs.status = StatusCode.StatusCode_OK
                cs.team_id = team["team_id"]
                cs.can_start = new_can_start
                mp_team.broadcast(team, MsgId.MPBeaconCanStartNotice, cs)  # 2430

        session.send(
            MsgId.MPBeaconPlayerReadyRsp, rsp, packet_id
        )  # 2469,2470 信标处准备
