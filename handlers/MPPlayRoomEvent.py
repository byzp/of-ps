import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPPlayRoomEventReq,
    MPPlayRoomEventRsp,
    MPPlayRoomEventNotice,
    MPPlayRoomEventType,
    MPPlayRoomSettlementNotice,
    MPBeaconStatus,
    StatusCode,
)

import server.mp_team as mp_team


@packet_handler(MsgId.MPPlayRoomEventReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPPlayRoomEventReq()
        req.ParseFromString(data)

        rsp = MPPlayRoomEventRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is not None and team["room"] is not None and req.events:
                # 把事件原样转发给队内其他成员
                notice = MPPlayRoomEventNotice()
                notice.status = StatusCode.StatusCode_OK
                for ev in req.events:
                    notice.events.add().CopyFrom(ev)
                mp_team.broadcast(
                    team, MsgId.MPPlayRoomEventNotice, notice, exclude=session.player_id
                )  # 2504

                # 收到 GameEnd 事件时做一次简单结算
                for ev in req.events:
                    if ev.event_type == MPPlayRoomEventType.MPPlayRoomEvent_GameEnd:
                        room = team["room"]
                        # 每个成员客户端都可能上报 GameEnd, 结算只做一次,
                        # 用 ended 标记防止重复广播(room 随每局重建, 无需复位)
                        if room.get("ended"):
                            break
                        room["ended"] = True
                        settle = MPPlayRoomSettlementNotice()
                        settle.status = StatusCode.StatusCode_OK
                        settle.gameplay_id = team["gameplay_id"]
                        settle.play_mode = team["game_mode"]
                        settle.rank.star = ev.star
                        settle.total_consume_time = max(
                            0, int(time.time() * 1000) - room["game_start_time"]
                        )
                        mp_team.broadcast(
                            team, MsgId.MPPlayRoomSettlementNotice, settle
                        )  # 2514
                        # 游戏结束, 信标状态回到已放置
                        if team["beacon"] is not None:
                            team["beacon"][
                                "status"
                            ] = MPBeaconStatus.MPBeaconStatus_PLACED
                        break

        session.send(MsgId.MPPlayRoomEventRsp, rsp, packet_id)  # 2501,2502 房间事件
