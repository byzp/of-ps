from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import time

from proto.net_pb2 import (
    DungeonEnterReq,
    DungeonEnterRsp,
    StatusCode,
    ServerSceneSyncDataNotice,
    StatusCode,
    SceneActionType,
)

import server.scene_data as scene_data
from utils.pb_create import make_SceneTeam
from utils.res_loader import res


@packet_handler(MsgId.DungeonEnterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonEnterReq()
        req.ParseFromString(data)

        rsp = DungeonEnterRsp()
        rsp.status = StatusCode.StatusCode_OK
        char_ids = []
        char_ids.append(req.char1)
        char_ids.append(req.char2)
        char_ids.append(req.char3)
        make_SceneTeam(session.player_id, char_ids, rsp.team)
        rsp.dungeon_data.dungeon_id = req.dungeon_id
        rsp.dungeon_data.enter_times = 1
        rsp.dungeon_data.char1 = req.char1
        rsp.dungeon_data.char2 = req.char2
        rsp.dungeon_data.char3 = req.char3
        rsp.dungeon_data.last_enter_time = int(time.time())
        # rsp.dungeon_data.pos.CopyFrom(req.pos)
        # rsp.dungeon_data.rot.CopyFrom(req.rot)
        session.dungeon[0] = req.dungeon_id

        find = False
        for i in res["Abyss"]["abyss_stage"]["datas"]:
            for ii in i["abyss_stage_group_info"]:
                if ii["dungeon_i_d"] == req.dungeon_id:
                    if ii.get("is_double_team"):
                        session.dungeon[3] == 0
                    find = True
                    break
            if find:
                break
        session.send(MsgId.DungeonEnterRsp, rsp, packet_id)

        # 向其他玩家广播离开事件
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = SceneActionType.SceneActionType_LEAVE
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)
