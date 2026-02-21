from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    DungeonExitReq,
    DungeonExitRsp,
    SceneDataNotice,
    PackNotice,
    StatusCode,
    SceneActionType,
    ServerSceneSyncDataNotice,
)

import server.scene_data as scene_data
from utils.pb_create import make_SceneDataNotice

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonExitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonExitReq()
        req.ParseFromString(data)

        rsp = DungeonExitRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scene_id = session.scene_id

        session.send(MsgId.DungeonExitRsp, rsp, packet_id)

        # 更新场景
        rsp = SceneDataNotice()
        rsp.CopyFrom(make_SceneDataNotice(session))
        session.send(MsgId.SceneDataNotice, rsp, 0)

        # 回花园时将临时背包物品更新到仓库
        if session.scene_id == 9999:
            rsp = PackNotice()
            rsp.status = StatusCode.StatusCode_OK
            rsp.is_clear_temp_pack = True
            session.send(MsgId.PackNotice, rsp, 0)
            session.temp_pack.clear()

        # 广播加入消息
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = SceneActionType.SceneActionType_ENTER
        sd.player.CopyFrom(session.scene_player)
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)
