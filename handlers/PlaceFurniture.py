from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import (
    EBagItemTag,
    ItemDetail,
    PackNotice,
    PlaceFurnitureReq,
    PlaceFurnitureRsp,
    SceneGardenFurnitureUpdateNotice,
    StatusCode,
)
from server import scene_data
from utils import garden_state
import utils.db as db
from utils import achieve_track, item_mgr
from utils.res_loader import res


@packet_handler(MsgId.PlaceFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlaceFurnitureReq()
        req.ParseFromString(data)
        rsp = PlaceFurnitureRsp()
        if db.get_furniture(session.scene_id, session.channel_id, session.player_id, req.furniture_id):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        blob = db.get_item_detail(session.player_id, req.furniture_item_id)
        if not isinstance(blob, (bytes, bytearray)):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        item = ItemDetail()
        item.ParseFromString(blob)
        home_items = {row.get('item_i_d') for row in res['HomeItem']['home_item']['datas']}
        if req.furniture_item_id not in home_items or item.main_item.item_tag != EBagItemTag.EBagItemTag_Furniture or item.main_item.base_item.num < 1:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        if session.scene_id != 9999 or session.channel_id != session.player_id or req.furniture_id <= 0:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        current, limit = garden_state.adjust_furniture_count(session.player_id, 0)
        if current >= limit:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        with item_mgr.player_lock(session.player_id), db.transaction():
            if not item_mgr.consume_items(session.player_id, [(req.furniture_item_id, 1)], pack_notice=pack, session=session):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            else:
                details = rsp.furniture_details_info
                details.furniture_id = req.furniture_id
                details.furniture_item_id = req.furniture_item_id
                details.pos.CopyFrom(req.pos)
                details.rotation.CopyFrom(req.rot)
                details.layer_num = req.layer_num
                db.set_furniture(session.scene_id, session.channel_id, session.player_id, req.furniture_id, details.SerializeToString())
                garden_state.adjust_furniture_count(session.player_id, 1)
                rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        achieve_track.report(session, 'place_furniture')
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
        notice = SceneGardenFurnitureUpdateNotice(status=StatusCode.StatusCode_OK)
        notice.furniture_info.CopyFrom(rsp.furniture_details_info)
        for other in scene_data.get_session():
            if other.scene_id == session.scene_id and other.channel_id == session.channel_id:
                other.send(MsgId.SceneGardenFurnitureUpdateNotice, notice, 0)
