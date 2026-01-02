from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as ChangeSceneChannelReq_pb2
import proto.OverField_pb2 as ChangeSceneChannelRsp_pb2
import proto.OverField_pb2 as SceneDataNotice_pb2
import proto.OverField_pb2 as ServerSceneSyncDataNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as pb

import server.scene_data as scene_data
from utils.pb_create import make_SceneDataNotice

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangeSceneChannelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeSceneChannelReq_pb2.ChangeSceneChannelReq()
        req.ParseFromString(data)

        # 向其他玩家广播离开事件
        notice = ServerSceneSyncDataNotice_pb2.ServerSceneSyncDataNotice()
        notice.status = StatusCode_pb2.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = pb.SceneActionType_LEAVE
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)

        session.scene_id = req.scene_id
        session.channel_id = req.channel_label or 1

        rsp = ChangeSceneChannelRsp_pb2.ChangeSceneChannelRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.scene_id = req.scene_id
        rsp.channel_id = session.channel_id
        rsp.channel_label = session.channel_id
        rsp.password_allow_time = 0
        rsp.target_player_id = req.target_player_label

        session.send(MsgId.ChangeSceneChannelRsp, rsp, packet_id)

        # 更新场景
        rsp = SceneDataNotice_pb2.SceneDataNotice()
        rsp.CopyFrom(make_SceneDataNotice(session))
        session.send(MsgId.SceneDataNotice, rsp, 0)

        # 回花园时将临时背包物品更新到仓库
        if req.scene_id == 9999:
            rsp = PackNotice_pb2.PackNotice()
            rsp.status = StatusCode_pb2.StatusCode_OK
            rsp.is_clear_temp_pack = True
            session.send(MsgId.PackNotice, rsp, 0)
            session.temp_pack.clear()

        # 广播加入消息
        notice = pb.ServerSceneSyncDataNotice()
        notice.status = pb.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = pb.SceneActionType_ENTER
        sd.player.CopyFrom(session.scene_player)
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)
