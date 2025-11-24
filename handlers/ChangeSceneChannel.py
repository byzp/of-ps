from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeSceneChannelReq_pb2
import proto.OverField_pb2 as ChangeSceneChannelRsp_pb2
import proto.OverField_pb2 as SceneDataNotice_pb2
import proto.OverField_pb2 as ServerSceneSyncDataNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import server.scene_data as scene_data

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeSceneChannelReq)
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
        scene_data.up_scene_action(
            session.scene_id, session.channel_id, notice.SerializeToString()
        )

        session.scene_id = req.scene_id
        session.channel_id = req.channel_label

        rsp = ChangeSceneChannelRsp_pb2.ChangeSceneChannelRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.scene_id = req.scene_id
        rsp.channel_id = req.channel_label
        rsp.channel_label = req.channel_label
        rsp.password_allow_time = 0
        rsp.target_player_id = req.target_player_label

        session.send(CmdId.ChangeSceneChannelRsp, rsp, packet_id)

        # 更新场景
        rsp = SceneDataNotice_pb2.SceneDataNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        data = rsp.data
        data.scene_id = session.scene_id

        data.players.add().CopyFrom(session.scene_player)
        for i in scene_data.get_and_up_players(
            session.scene_id, session.channel_id, session.player_id
        ):
            tmp = ServerSceneSyncDataNotice_pb2.ServerSceneSyncDataNotice()
            tmp.ParseFromString(i)
            data.players.add().CopyFrom(tmp.data[0].server_data[0].player)
        data.channel_id = session.channel_id
        data.tod_time = 0
        data.channel_label = session.channel_id
        session.send(CmdId.SceneDataNotice, rsp, packet_id)
