from utils import item_mgr

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TakeOutFurnitureReq,
    TakeOutFurnitureRsp,
    FurnitureDetailsInfo,
    ItemDetail,
    SceneGardenFurnitureRemoveNotice,
    StatusCode,
)
import utils.db as db
from server import scene_data

"""
# 收回家具 1697 1698
# is_put_in_package=True 时家具道具归还背包(否则仅移除摆放)
# 广播 SceneGardenFurnitureRemoveNotice 给同场景频道玩家
"""


@packet_handler(MsgId.TakeOutFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TakeOutFurnitureReq()
        req.ParseFromString(data)

        rsp = TakeOutFurnitureRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.furniture_id = req.furniture_id

        row = db.get_furniture(
            session.scene_id, session.channel_id, session.player_id, req.furniture_id
        )
        if not row:
            rsp.status = StatusCode.StatusCode_FURNITURE_NOT_EXIST
            session.send(MsgId.TakeOutFurnitureRsp, rsp, packet_id)
            return

        details = FurnitureDetailsInfo()
        details.ParseFromString(row[-1])

        db.del_furniture(
            session.scene_id, session.channel_id, session.player_id, req.furniture_id
        )

        # 归还家具道具(客户端勾选"放入背包")
        if req.is_put_in_package and details.furniture_item_id:

            item_mgr.grant_items(
                session.player_id, [(details.furniture_item_id, 1)], session=session
            )

        session.send(MsgId.TakeOutFurnitureRsp, rsp, packet_id)

        # 场景广播移除
        notice = SceneGardenFurnitureRemoveNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.furniture_id = req.furniture_id
        notice.item_id = details.furniture_item_id
        for s in scene_data.get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.SceneGardenFurnitureRemoveNotice, notice, 0)
