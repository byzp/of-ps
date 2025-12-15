from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as ChangeMusicalItemReq_pb2
import proto.OverField_pb2 as ChangeMusicalItemRsp_pb2
import proto.OverField_pb2 as Scene_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

from server.scene_data import up_scene_action
import server.notice_sync as notice_sync

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangeMusicalItemReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeMusicalItemReq_pb2.ChangeMusicalItemReq()
        req.ParseFromString(data)

        rsp = ChangeMusicalItemRsp_pb2.ChangeMusicalItemRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        if req.musical_item_instance_id:
            rsp.musical_item_instance_id = req.musical_item_instance_id
            rsp.musical_item_id = req.musical_item_instance_id
        session.send(MsgId.ChangeMusicalItemRsp, rsp, packet_id)  # 2671,2672

        notice = Scene_pb2.ServerSceneSyncDataNotice()
        notice.status = StatusCode_pb2.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.player_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = pb.SceneActionType_UPDATE_MUSICAL_ITEM
        session.scene_player.musical_item_id = req.musical_item_instance_id
        session.scene_player.musical_item_instance_id = req.musical_item_instance_id
        session.scene_player.source = req.source
        server_data_entry.player.CopyFrom(session.scene_player)
        up_scene_action(
            session.scene_id, session.channel_id, notice.SerializeToString()
        )

        # 视为完成登录，同步场景玩家并广播加入事件
        if session.logged_in == False:
            session.logged_in = True

            notice = pb.ServerSceneSyncDataNotice()
            notice.status = pb.StatusCode_OK
            d = notice.data.add()
            d.player_id = session.player_id
            sd = d.server_data.add()
            sd.action_type = pb.SceneActionType_ENTER
            sd.player.CopyFrom(session.scene_player)
            res = notice.SerializeToString()
            up_scene_action(session.scene_id, session.channel_id, res)

            # 同步时间
            rsp = pb.ServerSceneSyncDataNotice()
            rsp.status = StatusCode_pb2.StatusCode_OK
            tmp = rsp.data.add().server_data.add()
            tmp.action_type = pb.SceneActionType_TOD_UPDATE
            tmp.tod_time = int(notice_sync.tod_time)
            session.send(MsgId.ServerSceneSyncDataNotice, rsp, 0)
