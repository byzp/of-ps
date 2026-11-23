from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GardenFurnitureSaveReq, GardenFurnitureSaveRsp, StatusCode
import utils.db as db
import utils.garden_state as garden_state

"""
# 保存当前家具布置到方案 2615 2616
"""


@packet_handler(MsgId.GardenFurnitureSaveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GardenFurnitureSaveReq()
        req.ParseFromString(data)

        rsp = GardenFurnitureSaveRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scheme_id = req.scheme_id

        # 把当前场景内自己放置的家具快照存入方案
        furnitures = []
        for row in db.get_furniture(session.scene_id, session.channel_id):
            if row[2] == session.player_id:
                furnitures.append((row[3], row[4]))
        garden_state.save_scheme(session.player_id, req.scheme_id, furnitures)

        session.send(MsgId.GardenFurnitureSaveRsp, rsp, packet_id)  # 2615,2616
