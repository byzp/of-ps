from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPPlayRoomExitReq,
    MPPlayRoomExitRsp,
    MPPlayRoomExitNotice,
    MPBeaconStatus,
    StatusCode,
)

import server.mp_team as mp_team


@packet_handler(MsgId.MPPlayRoomExitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPPlayRoomExitReq()
        req.ParseFromString(data)

        rsp = MPPlayRoomExitRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None or team["room"] is None:
                rsp.status = StatusCode.StatusCode_PLAYER_NOT_IN_MP_ROOM
            else:
                room = team["room"]
                rsp.team_id = team["team_id"]
                room["ready"].discard(session.player_id)
                room["exited"].add(session.player_id)
                # 成员准备状态重置, 回到信标待命
                team["members"][session.player_id]["is_ready"] = False

                # 通知其他成员有人退出房间
                notice = MPPlayRoomExitNotice()
                notice.status = StatusCode.StatusCode_OK
                notice.team_id = team["team_id"]
                notice.player_id = session.player_id
                mp_team.broadcast(
                    team, MsgId.MPPlayRoomExitNotice, notice, exclude=session.player_id
                )  # 2519

                # 全员退出后销毁房间, 信标回到已放置状态
                if room["exited"] >= set(team["members"].keys()):
                    team["room"] = None
                    if team["beacon"] is not None:
                        team["beacon"]["status"] = MPBeaconStatus.MPBeaconStatus_PLACED

        session.send(MsgId.MPPlayRoomExitRsp, rsp, packet_id)  # 2517,2518 退出房间
