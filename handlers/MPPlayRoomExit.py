from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import MPPlayRoomExitReq, MPPlayRoomExitRsp, MPPlayRoomExitNotice, MPBeaconStatus, StatusCode
import server.mp_team as mp_team
from server import minigames


@packet_handler(MsgId.MPPlayRoomExitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPPlayRoomExitReq()
        req.ParseFromString(data)
        rsp = MPPlayRoomExitRsp()
        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None or team["room"] is None:
                rsp.status = StatusCode.StatusCode_PLAYER_NOT_IN_MP_ROOM
            else:
                room = team["room"]
                if session.player_id in room["exited"]:
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                else:
                    minigames.exit_member(team, session.player_id)
                    rsp.team_id = team["team_id"]
                    room["ready"].discard(session.player_id)
                    room["exited"].add(session.player_id)
                    team["members"][session.player_id]["is_ready"] = False
                    notice = MPPlayRoomExitNotice(
                        status=StatusCode.StatusCode_OK,
                        team_id=team["team_id"], player_id=session.player_id,
                    )
                    mp_team.broadcast(team, MsgId.MPPlayRoomExitNotice, notice, exclude=session.player_id)
                    if room["exited"] >= set(team["members"]):
                        team["room"] = None
                        if team["beacon"] is not None:
                            team["beacon"]["status"] = MPBeaconStatus.MPBeaconStatus_PLACED
                    mp_team._persist()
                    rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.MPPlayRoomExitRsp, rsp, packet_id)
