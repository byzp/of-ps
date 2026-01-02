from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

import proto.OverField_pb2 as DungeonEnterReq_pb2
import proto.OverField_pb2 as DungeonEnterRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as ServerSceneSyncDataNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import server.scene_data as scene_data
from utils.pb_create import make_SceneTeam

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonEnterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonEnterReq_pb2.DungeonEnterReq()
        req.ParseFromString(data)

        rsp = DungeonEnterRsp_pb2.DungeonEnterRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        char_ids = []
        char_ids.append(req.char1)
        char_ids.append(req.char2)
        char_ids.append(req.char3)
        rsp.team.CopyFrom(make_SceneTeam(session.player_id, char_ids))
        rsp.dungeon_data.dungeon_id = req.dungeon_id
        rsp.dungeon_data.enter_times = 1
        rsp.dungeon_data.char1 = req.char1
        rsp.dungeon_data.char2 = req.char2
        rsp.dungeon_data.char3 = req.char3
        rsp.dungeon_data.last_enter_time = int(time.time())
        rsp.dungeon_data.pos.CopyFrom(req.pos)
        rsp.dungeon_data.rot.CopyFrom(req.rot)

        session.send(MsgId.DungeonEnterRsp, rsp, packet_id)

        # 向其他玩家广播离开事件
        notice = ServerSceneSyncDataNotice_pb2.ServerSceneSyncDataNotice()
        notice.status = StatusCode_pb2.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = pb.SceneActionType_LEAVE
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)
