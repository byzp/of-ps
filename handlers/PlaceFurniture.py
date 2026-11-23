from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    PlaceFurnitureReq,
    PlaceFurnitureRsp,
    EBagItemTag,
    ItemDetail,
    PackNotice,
    SceneGardenFurnitureUpdateNotice,
    StatusCode,
)
from server import scene_data as _sd
import utils.db as db
from utils import achieve_track
from utils.res_loader import res

"""
# 放置家具 1681 1682
"""


@packet_handler(MsgId.PlaceFurnitureReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlaceFurnitureReq()
        req.ParseFromString(data)

        rsp = PlaceFurnitureRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 家具道具必须已拥有并消耗一件(tag=Furniture)
        item_blob = db.get_item_detail(session.player_id, req.furniture_item_id)
        if not item_blob or not isinstance(item_blob, (bytes, bytearray)):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        _fd = ItemDetail()
        _fd.ParseFromString(item_blob)
        _home_items = {
            h.get("item_i_d")
            for h in res.get("HomeItem", {}).get("home_item", {}).get("datas", [])
        }
        if _home_items and req.furniture_item_id not in _home_items:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        if _fd.main_item.item_tag != EBagItemTag.EBagItemTag_Furniture:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        if _fd.main_item.base_item.num < 1:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
            return
        _fd.main_item.base_item.num -= 1
        db.set_item_detail(
            session.player_id,
            _fd.SerializeToString(),
            req.furniture_item_id,
            None,
        )
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        rsp1.items.add().CopyFrom(_fd)

        # 成就: 摆放家具
        achieve_track.report(session, "place_furniture")

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

        # 持久化家具到 furnitures 表
        db.set_furniture(
            session.scene_id,
            session.channel_id,
            session.player_id,
            req.furniture_id,
            furniture_details.SerializeToString(),
        )

        session.send(MsgId.PlaceFurnitureRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)

        # 场景广播: 家具更新(同场景频道玩家)

        _notice = SceneGardenFurnitureUpdateNotice()
        _notice.status = StatusCode.StatusCode_OK
        _notice.furniture_info.CopyFrom(rsp.furniture_details_info)
        for _s in _sd.get_session():
            if _s.scene_id == session.scene_id and _s.channel_id == session.channel_id:
                _s.send(MsgId.SceneGardenFurnitureUpdateNotice, _notice, 0)
