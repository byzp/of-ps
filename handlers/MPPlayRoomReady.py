import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPPlayRoomReadyReq,
    MPPlayRoomReadyRsp,
    MPPlayRoomEventNotice,
    MPPlayRoomEventType,
    StatusCode,
)

import server.mp_team as mp_team


@packet_handler(MsgId.MPPlayRoomReadyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPPlayRoomReadyReq()
        req.ParseFromString(data)

        rsp = MPPlayRoomReadyRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None or team["room"] is None:
                rsp.status = StatusCode.StatusCode_PLAYER_NOT_IN_MP_ROOM
                session.send(MsgId.MPPlayRoomReadyRsp, rsp, packet_id)  # 2505,2506
                return

            room = team["room"]
            if req.ready:
                room["ready"].add(session.player_id)
            else:
                room["ready"].discard(session.player_id)

            # 全员加载完毕后广播 GameStart 事件正式开局
            if (
                req.ready
                and not room.get("started")
                and room["ready"] >= set(team["members"].keys())
            ):
                room["started"] = True
                room["game_start_time"] = int(time.time() * 1000)
                notice = MPPlayRoomEventNotice()
                notice.status = StatusCode.StatusCode_OK
                ev = notice.events.add()
                ev.event_type = MPPlayRoomEventType.MPPlayRoomEvent_GameStart
                ev.time = room["game_start_time"]
                ev.game_start_time = room["game_start_time"]
                ev.play_mode = team["game_mode"]
                mp_team.broadcast(team, MsgId.MPPlayRoomEventNotice, notice)  # 2504

        session.send(MsgId.MPPlayRoomReadyRsp, rsp, packet_id)  # 2505,2506 房间内准备
