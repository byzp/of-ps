from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import MPSwapCharacterReq, MPSwapCharacterRsp, StatusCode

import server.mp_team as mp_team
import utils.db as db


@packet_handler(MsgId.MPSwapCharacterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MPSwapCharacterReq()
        req.ParseFromString(data)

        rsp = MPSwapCharacterRsp()
        rsp.status = StatusCode.StatusCode_OK

        with mp_team.lock:
            team = mp_team.get_team_by_player(session.player_id)
            if team is None:
                rsp.status = StatusCode.StatusCode_MP_NOT_IN_TEAM
            else:
                member = team["members"][session.player_id]
                if member["character_id"] == req.character_id:
                    rsp.status = StatusCode.StatusCode_MP_CHARACTER_UNCHANGED
                else:
                    blobs = db.get_characters(session.player_id, req.character_id)
                    if not blobs:
                        # 未拥有该角色
                        rsp.status = StatusCode.StatusCode_MP_CHARACTER_INVALID
                    else:
                        member["character_id"] = req.character_id
                        rsp.new_info.character.ParseFromString(blobs[0])
                        # 通知其他成员角色变化
                        mp_team.notify_members(team, exclude=session.player_id)  # 2458

        session.send(MsgId.MPSwapCharacterRsp, rsp, packet_id)  # 2412,2413 切换出战角色
