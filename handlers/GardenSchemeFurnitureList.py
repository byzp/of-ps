from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GardenSchemeFurnitureListReq,
    GardenSchemeFurnitureListRsp,
    FurnitureDetailsInfo,
    StatusCode,
)
import utils.garden_state as garden_state
import utils.db as db

"""
# 查询家具方案内的家具物品列表 2619 2620
"""


@packet_handler(MsgId.GardenSchemeFurnitureListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenSchemeFurnitureListReq()
        req.ParseFromString(data)

        rsp = GardenSchemeFurnitureListRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scheme_id = req.scheme_id

        scheme = garden_state.get_scheme(session.player_id, req.scheme_id)
        if scheme is not None:
            for _, blob in scheme["furnitures"]:
                tmp = FurnitureDetailsInfo()
                tmp.ParseFromString(blob)
                rsp.furniture_item_id.append(tmp.furniture_item_id)

        session.send(MsgId.GardenSchemeFurnitureListRsp, rsp, packet_id)  # 2619,2620
