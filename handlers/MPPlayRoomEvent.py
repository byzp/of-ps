import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import MPPlayRoomEventReq, MPPlayRoomEventRsp, MPPlayRoomEventNotice, MPPlayRoomEventType, MPBeaconStatus, StatusCode
import server.mp_team as mp_team
from server import minigames


@packet_handler(MsgId.MPPlayRoomEventReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPPlayRoomEventReq()
        req.ParseFromString(data)
        rsp = MPPlayRoomEventRsp()
        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None or team["room"] is None:
                rsp.status = StatusCode.StatusCode_PLAYER_NOT_IN_MP_ROOM
                session.send(MsgId.MPPlayRoomEventRsp, rsp, packet_id)
                return
            room = team["room"]
            if session.player_id in room["exited"]:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.MPPlayRoomEventRsp, rsp, packet_id)
                return
            run = minigames.ensure_run(team)
            if run["status"] == "settled":
                # 重复/重连上报只确认，不重复发放或广播结算。
                rsp.status = StatusCode.StatusCode_OK
                session.send(MsgId.MPPlayRoomEventRsp, rsp, packet_id)
                return
            if any(event.event_type == MPPlayRoomEventType.MPPlayRoomEvent_GameStart for event in req.events):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.MPPlayRoomEventRsp, rsp, packet_id)
                return
            if req.events:
                notice = MPPlayRoomEventNotice(status=StatusCode.StatusCode_OK)
                for event in req.events:
                    notice.events.add().CopyFrom(event)
                mp_team.broadcast(team, MsgId.MPPlayRoomEventNotice, notice, exclude=session.player_id)
            for event in req.events:
                if event.event_type != MPPlayRoomEventType.MPPlayRoomEvent_GameEnd:
                    continue
                try:
                    run, changed = minigames.settle(team, int(event.star))
                except minigames.RoomRewardConfigError:
                    rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                    break
                except minigames.RoomStateError:
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                    break
                if changed:
                    room["ended"] = True
                    for player_id in sorted(int(pid) for pid in run["members"]):
                        mp_team.send_to_players(
                            [player_id], MsgId.MPPlayRoomSettlementNotice,
                            minigames.settlement_notice(run, player_id),
                        )
                    if team["beacon"] is not None:
                        team["beacon"]["status"] = MPBeaconStatus.MPBeaconStatus_PLACED
                    mp_team._persist()
                break
            else:
                rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.MPPlayRoomEventRsp, rsp, packet_id)
