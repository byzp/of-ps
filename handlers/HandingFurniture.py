from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import HandingFurnitureReq, HandingFurnitureRsp, StatusCode
import utils.db as db
from utils import achieve_track


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
        # 用玩家实例 id 分配器分配家具实例 id, 与背包/家具持久化同一 id 体系
        rsp.furniture_id = db.get_instance_id(session.player_id)

        achieve_track.report(session, "craft_furniture_process")

        # HandingFurniture* -> SendAction -> SceneInterActionPlayStatus 从背包取出
        # PlaceFurniture 放置
        session.send(MsgId.HandingFurnitureRsp, rsp, packet_id)
