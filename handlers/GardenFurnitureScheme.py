from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GardenFurnitureSchemeReq, GardenFurnitureSchemeRsp, StatusCode
import utils.garden_state as garden_state
import utils.db as db

"""
# 查询家具方案列表 2623 2624
"""


@packet_handler(MsgId.GardenFurnitureSchemeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenFurnitureSchemeReq()
        req.ParseFromString(data)

        rsp = GardenFurnitureSchemeRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 方案经 garden_state -> db.get_schemes/set_schemes 持久化
        for scheme_id, name in garden_state.get_scheme_names(session.player_id).items():
            rsp.schemes[scheme_id] = name

        session.send(MsgId.GardenFurnitureSchemeRsp, rsp, packet_id)  # 2623,2624
