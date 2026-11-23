import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPGameStartReq,
    MPGameStartRsp,
    MPRoomEnterNotice,
    MPRoomAssignHostNotice,
    MPBeaconStatus,
    StatusCode,
)

import server.mp_team as mp_team


@packet_handler(MsgId.MPGameStartReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPGameStartReq()
        req.ParseFromString(data)

        rsp = MPGameStartRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
            elif team["leader"] != session.player_id:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NOT_LEADER
            elif team["room"] is not None:
                rsp.status = StatusCode.StatusCode_MP_TEAM_GAME_STARTED
            elif not mp_team.can_start(team):
                rsp.status = StatusCode.StatusCode_MP_TEAM_NOT_READY
            else:
                rsp.team_id = team["team_id"]
                # 创建游戏房间(room_id 直接复用 team_id)
                team["room"] = {
                    "game_start_time": int(time.time() * 1000),
                    "ready": set(),
                    "exited": set(),
                    "fg_bytes": {},
                }
                if team["beacon"] is not None:
                    team["beacon"]["status"] = MPBeaconStatus.MPBeaconStatus_STARTED

                # 全体成员进入房间
                enter = MPRoomEnterNotice()
                enter.status = StatusCode.StatusCode_OK
                enter.room_info.is_ready = False
                enter.room_info.game_start_time = team["room"]["game_start_time"]
                mp_team.fill_mode_info(team, enter.game_mode_info)
                mp_team.broadcast(team, MsgId.MPRoomEnterNotice, enter)  # 2468

                # 指定队长为房主(P2P 同步的 host)
                host = MPRoomAssignHostNotice()
                host.status = StatusCode.StatusCode_OK
                host.room_id = team["team_id"]
                mp_team.send_to_players(
                    [team["leader"]], MsgId.MPRoomAssignHostNotice, host
                )  # 2465

        session.send(MsgId.MPGameStartRsp, rsp, packet_id)  # 2431,2432 开始多人游戏
