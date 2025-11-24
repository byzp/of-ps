from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as PlaceFurnitureReq_pb2
import proto.OverField_pb2 as PlaceFurnitureRsp_pb2

logger = logging.getLogger(__name__)


"""
# 放置家具 1681 1682
"""


@packet_handler(CmdId.PlaceFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlaceFurnitureReq_pb2.PlaceFurnitureReq()
        req.ParseFromString(data)

        rsp = PlaceFurnitureRsp_pb2.PlaceFurnitureRsp()

        rsp.status = TEST_DATA["status"]

        # 设置家具详情信息
        furniture_details = rsp.furniture_details_info
        furniture_details.furniture_id = req.furniture_id
        furniture_details.furniture_item_id = req.furniture_item_id

        # 设置位置信息
        furniture_details.pos.x = req.pos.x
        furniture_details.pos.y = req.pos.y
        furniture_details.pos.z = req.pos.z
        furniture_details.pos.decimal_places = req.pos.decimal_places

        # 设置旋转信息
        furniture_details.rotation.x = req.rot.x
        furniture_details.rotation.y = req.rot.y
        furniture_details.rotation.z = req.rot.z
        furniture_details.rotation.decimal_places = req.rot.decimal_places

        # 设置层级
        furniture_details.layer_num = req.layer_num

        session.send(CmdId.PlaceFurnitureRsp, rsp, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
