from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ChangeMusicalItemReq,
    ChangeMusicalItemRsp,
    ServerSceneSyncDataNotice,
    StatusCode,
    SceneActionType,
    ItemDetail,
)

from server.scene_data import up_scene_action
import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.ChangeMusicalItemReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeMusicalItemReq()
        req.ParseFromString(data)

        # 从背包按实例 id 解析真实的乐器物品 id
        musical_item_id = 0
        if req.musical_item_instance_id:
            blob = db.get_item_detail(
                session.player_id, None, req.musical_item_instance_id
            )
            if blob:
                item = ItemDetail()
                item.ParseFromString(blob)
                musical_item_id = item.main_item.item_id
            # 背包查不到该实例时 item_id 置 0, 不再用实例 id 冒充物品 id
            _musica = {
                m["i_d"]
                for m in res.get("HomeItem", {}).get("musica_item", {}).get("datas", [])
            }
            if musical_item_id and _musica and musical_item_id not in _musica:
                musical_item_id = 0

        rsp = ChangeMusicalItemRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.source = req.source
        if req.musical_item_instance_id:
            rsp.musical_item_instance_id = req.musical_item_instance_id
            rsp.musical_item_id = musical_item_id
        session.send(MsgId.ChangeMusicalItemRsp, rsp, packet_id)  # 2671,2672

        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.player_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = (
            SceneActionType.SceneActionType_UPDATE_MUSICAL_ITEM
        )
        session.scene_player.musical_item_id = musical_item_id
        session.scene_player.musical_item_instance_id = req.musical_item_instance_id
        session.scene_player.musical_item_source = req.source
        server_data_entry.player.CopyFrom(session.scene_player)
        up_scene_action(session.scene_id, session.channel_id, notice)
