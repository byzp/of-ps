from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ChangeMusicalItemReq,
    ChangeMusicalItemRsp,
    ServerSceneSyncDataNotice,
    StatusCode,
    SceneActionType,
)

from server.scene_data import up_scene_action


@packet_handler(MsgId.ChangeMusicalItemReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeMusicalItemReq()
        req.ParseFromString(data)

        rsp = ChangeMusicalItemRsp()
        rsp.status = StatusCode.StatusCode_OK
        if req.musical_item_instance_id:
            rsp.musical_item_instance_id = req.musical_item_instance_id
            rsp.musical_item_id = req.musical_item_instance_id
        session.send(MsgId.ChangeMusicalItemRsp, rsp, packet_id)  # 2671,2672

        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.player_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = (
            SceneActionType.SceneActionType_UPDATE_MUSICAL_ITEM
        )
        session.scene_player.musical_item_id = req.musical_item_instance_id
        session.scene_player.musical_item_instance_id = req.musical_item_instance_id
        session.scene_player.musical_item_source = req.source
        server_data_entry.player.CopyFrom(session.scene_player)
        up_scene_action(session.scene_id, session.channel_id, notice)
