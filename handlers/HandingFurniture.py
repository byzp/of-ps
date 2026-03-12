from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import random

from proto.net_pb2 import HandingFurnitureReq, HandingFurnitureRsp, StatusCode
import utils.db as db


@packet_handler(MsgId.HandingFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = HandingFurnitureReq()
        req.ParseFromString(data)

        rsp = HandingFurnitureRsp()
        item = db.get_item_detail(session.player_id, req.item_id)
        if not item:
            rsp.status = StatusCode.StatusCode_FURNITURE_NOT_EXIST
            session.send(MsgId.HandingFurnitureRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        rsp.furniture_id = random.randint(10000000000000000, 99999999999999999)

        # HandingFurniture* -> SendAction -> SceneInterActionPlayStatus 从背包取出
        # PlaceFurniture 放置
        # TakeOutFurniture 从地面搬起
        # TakeOutHandingFurniture 放回背包
        session.send(MsgId.HandingFurnitureRsp, rsp, packet_id)
