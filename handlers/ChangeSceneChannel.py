from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    ChangeSceneChannelReq,
    ChangeSceneChannelRsp,
    SceneDataNotice,
    ServerSceneSyncDataNotice,
    StatusCode,
    PackNotice,
    SceneActionType,
)

import server.scene_data as scene_data
from utils.pb_create import make_SceneDataNotice

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangeSceneChannelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeSceneChannelReq()
        req.ParseFromString(data)

        # 向其他玩家广播离开事件
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = SceneActionType.SceneActionType_LEAVE
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)

        session.scene_id = req.scene_id
        session.channel_id = req.channel_label or 1

        rsp = ChangeSceneChannelRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.scene_id = req.scene_id
        rsp.channel_id = session.channel_id
        rsp.channel_label = session.channel_id
        rsp.password_allow_time = 0
        rsp.target_player_id = req.target_player_label

        session.send(MsgId.ChangeSceneChannelRsp, rsp, packet_id)

        # 更新场景
        rsp = SceneDataNotice()
        rsp.CopyFrom(make_SceneDataNotice(session))
        session.send(MsgId.SceneDataNotice, rsp, 0)

        # 回花园时将临时背包物品更新到仓库
        if req.scene_id == 9999:
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
