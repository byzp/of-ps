from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GardenFurnitureRemoveAllReq,
    GardenFurnitureRemoveAllRsp,
    GardenFurnitureBatchUpdateNotice,
    StatusCode,
)
import utils.db as db
from server.scene_data import get_session

"""
# 移除花园内全部家具 2611 2612 -> 2614
"""


@packet_handler(MsgId.GardenFurnitureRemoveAllReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenFurnitureRemoveAllReq()
        req.ParseFromString(data)

        rsp = GardenFurnitureRemoveAllRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 删除当前场景内自己放置的全部家具
        for row in db.get_furniture(session.scene_id, session.channel_id):
            if row[2] == session.player_id:
                db.del_furniture(
                    session.scene_id, session.channel_id, session.player_id, row[3]
                )

        session.send(MsgId.GardenFurnitureRemoveAllRsp, rsp, packet_id)  # 2611,2612

        # 通知同场景频道玩家: 家具已清空
        notice = GardenFurnitureBatchUpdateNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.player_id = session.player_id
        notice.furniture_point_num = 0
        for s in get_session():
            if (
                s.scene_id == session.scene_id
                and s.channel_id == session.channel_id
                and s.player_id != session.player_id
            ):
                s.send(MsgId.GardenFurnitureBatchUpdateNotice, notice, 0)  # 2614
