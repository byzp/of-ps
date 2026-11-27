import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import MPPlayRoomReadyReq, MPPlayRoomReadyRsp, MPPlayRoomEventNotice, MPPlayRoomEventType, StatusCode
import server.mp_team as mp_team
from server import minigames


@packet_handler(MsgId.MPPlayRoomReadyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPPlayRoomReadyReq()
        req.ParseFromString(data)
        rsp = MPPlayRoomReadyRsp()
        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None or team["room"] is None:
                rsp.status = StatusCode.StatusCode_PLAYER_NOT_IN_MP_ROOM
                session.send(MsgId.MPPlayRoomReadyRsp, rsp, packet_id)
                return
            room = team["room"]
            if session.player_id in room["exited"]:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.MPPlayRoomReadyRsp, rsp, packet_id)
                return
            minigames.ensure_run(team)
            if req.ready:
                room["ready"].add(session.player_id)
            else:
                room["ready"].discard(session.player_id)
            active_members = set(team["members"]) - set(room["exited"])
            if req.ready and active_members and room["ready"] >= active_members and not room.get("started"):
                room["started"] = True
                room["game_start_time"] = int(time.time() * 1000)
                minigames.mark_started(team, room["game_start_time"])
                notice = MPPlayRoomEventNotice(status=StatusCode.StatusCode_OK)
                event = notice.events.add()
                event.event_type = MPPlayRoomEventType.MPPlayRoomEvent_GameStart
                event.time = room["game_start_time"]
                event.game_start_time = room["game_start_time"]
                event.play_mode = team["game_mode"]
                mp_team.broadcast(team, MsgId.MPPlayRoomEventNotice, notice)
            mp_team._persist()
            rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.MPPlayRoomReadyRsp, rsp, packet_id)
