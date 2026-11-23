from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MPBeaconActionReq,
    MPBeaconActionRsp,
    MPTeamBeaconNotice,
    SceneMPBeaconNotice,
    MPBeaconAction,
    MPBeaconStatus,
    StatusCode,
    Vector3,
)

import server.mp_team as mp_team
from server.scene_data import get_session


@packet_handler(MsgId.MPBeaconActionReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPBeaconActionReq()
        req.ParseFromString(data)

        rsp = MPBeaconActionRsp()
        rsp.status = StatusCode.StatusCode_OK

        team_notice = None
        scene_notice = None
        target_scene = None  # (scene_id, channel_id) 场景广播目标
        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
                session.send(MsgId.MPBeaconActionRsp, rsp, packet_id)  # 2414,2415
                return
            if team["leader"] != session.player_id:
                rsp.status = StatusCode.StatusCode_MP_TEAM_NOT_LEADER
                session.send(MsgId.MPBeaconActionRsp, rsp, packet_id)  # 2414,2415
                return

            beacon = team["beacon"]
            # 广播目标 = 信标实际放置的场景(队长可能已切场景);
            # PLACE 时信标尚不存在, 用队长当前场景。需在 RETRIVE 清掉 beacon 前取值
            if beacon is not None:
                target_scene = (beacon["scene_id"], beacon["channel_id"])
            else:
                target_scene = (session.scene_id, session.channel_id)
            if req.action == MPBeaconAction.MPBeaconAction_PLACE:
                if beacon is not None:
                    rsp.status = StatusCode.StatusCode_MP_BEACON_DUPLICATED
                else:
                    pos = Vector3()
                    pos.CopyFrom(req.position)
                    rot = Vector3()
                    rot.CopyFrom(req.rotation)
                    team["beacon"] = {
                        "status": MPBeaconStatus.MPBeaconStatus_PLACED,
                        "position": pos,
                        "rotation": rot,
                        "scene_id": session.scene_id,
                        "channel_id": session.channel_id,
                        "owner_id": session.player_id,
                    }
            elif req.action == MPBeaconAction.MPBeaconAction_MOVE:
                if beacon is None:
                    rsp.status = StatusCode.StatusCode_MP_BEACON_NOT_EXIST
                else:
                    beacon["position"].CopyFrom(req.position)
                    beacon["rotation"].CopyFrom(req.rotation)
                    beacon["status"] = MPBeaconStatus.MPBeaconStatus_PLACED
            elif req.action == MPBeaconAction.MPBeaconAction_RETRIVE:
                if beacon is None:
                    rsp.status = StatusCode.StatusCode_MP_BEACON_NOT_EXIST
                else:
                    team["beacon"] = None
            elif req.action == MPBeaconAction.MPBeaconAction_CALL_IN:
                if beacon is None:
                    rsp.status = StatusCode.StatusCode_MP_BEACON_NOT_PLACED
                else:
                    beacon["status"] = MPBeaconStatus.MPBeaconStatus_CALLING_IN
            else:
                rsp.status = StatusCode.StatusCode_BAD_REQ

            rsp.team_id = team["team_id"]
            mp_team.fill_beacon(team, rsp.beacon)

            if rsp.status == StatusCode.StatusCode_OK:
                # 队内信标状态同步
                team_notice = MPTeamBeaconNotice()
                team_notice.status = StatusCode.StatusCode_OK
                team_notice.team_id = team["team_id"]
                team_notice.beacon.CopyFrom(rsp.beacon)
                mp_team.broadcast(
                    team,
                    MsgId.MPTeamBeaconNotice,
                    team_notice,
                    exclude=session.player_id,
                )  # 2418

                # 同场景玩家可见的信标广播
                scene_notice = SceneMPBeaconNotice()
                scene_notice.status = StatusCode.StatusCode_OK
                scene_notice.beacons[team["team_id"]].CopyFrom(rsp.beacon)

        session.send(MsgId.MPBeaconActionRsp, rsp, packet_id)  # 2414,2415 信标操作

        if scene_notice is not None:
            # 不能用 up_action: 该队列的消费端(notice_sync)硬编码按 SendActionNotice
            # 发送并访问 from_player_id, 塞其他消息会让同步线程崩溃退出进程。
            for s in get_session():
                if s.scene_id == target_scene[0] and s.channel_id == target_scene[1]:
                    s.send(MsgId.SceneMPBeaconNotice, scene_notice, 0)  # 2424
