from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import MPTeamCreateReq, MPTeamCreateRsp, StatusCode

import server.mp_team as mp_team
import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.MPTeamCreateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPTeamCreateReq()
        req.ParseFromString(data)

        rsp = MPTeamCreateRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 模式校验(TeamGameplay.mode/mode_items.sub_mode_id)
        _modes = {
            m["i_d"]: m
            for m in res.get("TeamGameplay", {}).get("mode", {}).get("datas", [])
        }
        if _modes and req.mode_id not in _modes:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.MPTeamCreateRsp, rsp, packet_id)
            return
        if _modes and req.sub_mode_id:
            _subs = {
                s.get("sub_mode_id")
                for s in _modes[req.mode_id].get("mode_items", ()) or ()
            }
            if _subs and req.sub_mode_id not in _subs:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.MPTeamCreateRsp, rsp, packet_id)
                return

        with mp_team.lock:
            if mp_team.get_team_by_player(session.player_id) is not None:
                rsp.status = StatusCode.StatusCode_MP_ALREADY_IN_TEAM
                session.send(MsgId.MPTeamCreateRsp, rsp, packet_id)  # 2406,2407
                return

            team_name = req.team_name
            if not team_name:
                # 客户端未填名字时给个默认队名
                team_name = f"{session.player_name}的队伍"

            team = mp_team.create_team(
                session.player_id,
                team_name,
                req.mode_id,
                req.sub_mode_id,
                req.character_id,
            )
            mp_team.fill_team_detail(team, rsp.team_detail)

        session.send(MsgId.MPTeamCreateRsp, rsp, packet_id)  # 2406,2407 创建队伍
