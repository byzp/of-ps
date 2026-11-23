from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GardenFurnitureApplySchemeReq,
    GardenFurnitureApplySchemeRsp,
    GardenFurnitureBatchUpdateNotice,
    StatusCode,
)
import utils.db as db
import utils.garden_state as garden_state
from server.scene_data import get_session

"""
# 应用家具布置方案 2617 2618 -> 2614
"""


@packet_handler(MsgId.GardenFurnitureApplySchemeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenFurnitureApplySchemeReq()
        req.ParseFromString(data)

        rsp = GardenFurnitureApplySchemeRsp()
        rsp.scheme_id = req.scheme_id

        scheme = garden_state.get_scheme(session.player_id, req.scheme_id)
        if scheme is None:
            # 方案不存在(内存态, 重启后丢失)
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(
                MsgId.GardenFurnitureApplySchemeRsp, rsp, packet_id
            )  # 2617,2618
            return

        rsp.status = StatusCode.StatusCode_OK

        # 清空当前场景内自己放置的家具
        for row in db.get_furniture(session.scene_id, session.channel_id):
            if row[2] == session.player_id:
                db.del_furniture(
                    session.scene_id, session.channel_id, session.player_id, row[3]
                )

        # 写回方案快照
        notice = GardenFurnitureBatchUpdateNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.player_id = session.player_id
        for furniture_id, blob in scheme["furnitures"]:
            db.set_furniture(
                session.scene_id,
                session.channel_id,
                session.player_id,
                furniture_id,
                blob,
            )
            notice.new_furniture_list.add().ParseFromString(blob)
        notice.furniture_point_num = len(scheme["furnitures"])

        session.send(MsgId.GardenFurnitureApplySchemeRsp, rsp, packet_id)  # 2617,2618

        # 通知同场景频道玩家家具批量更新
        for s in get_session():
            if s.scene_id == session.scene_id and s.channel_id == session.channel_id:
                s.send(MsgId.GardenFurnitureBatchUpdateNotice, notice, 0)  # 2614
