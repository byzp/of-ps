from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as DungeonExitReq_pb2
import proto.OverField_pb2 as DungeonExitRsp_pb2
import proto.OverField_pb2 as SceneDataNotice_pb2
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import server.scene_data as scene_data
import server.notice_sync as notice_sync

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonExitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonExitReq_pb2.DungeonExitReq()
        req.ParseFromString(data)

        rsp = DungeonExitRsp_pb2.DungeonExitRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.scene_id = session.scene_id

        session.send(MsgId.DungeonExitRsp, rsp, packet_id)

        # 更新场景
        rsp = SceneDataNotice_pb2.SceneDataNotice()
        rsp.status = StatusCode_pb2.StatusCode_OK
        data = rsp.data
        data.scene_id = session.scene_id
        data.players.add().CopyFrom(session.scene_player)

        tmp = pb.ScenePlayer()
        for i in scene_data.get_scene_player(session.scene_id, session.channel_id):
            tmp.CopyFrom(i)
            data.players.add().CopyFrom(tmp)
        data.channel_id = session.channel_id
        data.tod_time = int(notice_sync.tod_time)
        data.channel_label = session.channel_id
        session.send(MsgId.SceneDataNotice, rsp, 0)

        # 回花园时将临时背包物品更新到仓库
        if session.scene_id == 9999:
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
        res = notice.SerializeToString()
        scene_data.up_scene_action(session.scene_id, session.channel_id, res)
