from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GardenFurnitureSchemeSetNameReq,
    GardenFurnitureSchemeSetNameRsp,
    StatusCode,
)
import utils.garden_state as garden_state
import utils.db as db

"""
# 设置家具方案名称 2621 2622
"""


@packet_handler(MsgId.GardenFurnitureSchemeSetNameReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenFurnitureSchemeSetNameReq()
        req.ParseFromString(data)

        rsp = GardenFurnitureSchemeSetNameRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scheme_id = req.scheme_id
        rsp.name = req.name

        garden_state.set_scheme_name(session.player_id, req.scheme_id, req.name)

        session.send(MsgId.GardenFurnitureSchemeSetNameRsp, rsp, packet_id)  # 2621,2622
