from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    SceneInterActionPlayStatusReq,
    SceneInterActionPlayStatusRsp,
    StatusCode,
    InterActionPushType,
    FurnitureDetailsInfo,
)

import utils.db as db


@packet_handler(MsgId.SceneInterActionPlayStatusReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SceneInterActionPlayStatusReq()
        req.ParseFromString(data)

        rsp = SceneInterActionPlayStatusRsp()
        rsp.status = StatusCode.StatusCode_OK
        if req.action_status.id not in [7001] or req.push_type in [
            0,
            1,
        ]:  # TODO 尚不明确的功能
            print(req)
            session.send(MsgId.SceneInterActionPlayStatusRsp, rsp, packet_id)
            return
        match req.action_status.id:
            case 7001:  # 放置家具
                if req.push_type == InterActionPushType.AddKeepingStatus:
                    furniture = db.get_furniture(
                        session.scene_id,
                        session.channel_id,
                        session.player_id,
                        req.action_status.value1,
                    )
                    if furniture:
                        db.del_furniture(
                            session.scene_id,
                            session.channel_id,
                            session.player_id,
                            req.action_status.value1,
                        )
                if req.push_type == InterActionPushType.RemovingStatus:
                    if req.action_status.value2:
                        tmp = FurnitureDetailsInfo()
                        tmp.furniture_id = req.action_status.value1
                        tmp.furniture_item_id = req.action_status.value2
                        tmp.pos.x = req.action_status.value3
                        tmp.pos.y = req.action_status.value4
                        tmp.pos.z = req.action_status.value5
                        tmp.rotation.y = req.action_status.value6
                        db.set_furniture(
                            session.scene_id,
                            session.channel_id,
                            session.player_id,
                            tmp.furniture_id,
                            tmp.SerializeToString(),
                        )

        session.send(MsgId.SceneInterActionPlayStatusRsp, rsp, packet_id)
