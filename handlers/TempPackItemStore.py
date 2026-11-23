from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TempPackItemStoreReq,
    TempPackItemStoreRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

import utils.db as db


@packet_handler(MsgId.TempPackItemStoreReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TempPackItemStoreReq()
        req.ParseFromString(data)

        rsp = TempPackItemStoreRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        # 拾取时已按 Inventory 预写入 items_s(见 TreasureBoxPickup),
        # 入库只需把会话内临时背包标记转正并清空临时背包
        for instance_id, blob in session.temp_pack:
            item = ItemDetail()
            item.ParseFromString(blob)
            item.pack_type = ItemDetail.PackType.PackType_Inventory
            item.main_item.temp_pack_index = 0
            if instance_id:
                raw = db.get_item_detail(session.player_id, None, instance_id)
            else:
                # 材料在拾取时已经累计入库，此处同步库存总量而非重复加数量。
                raw = db.get_item_detail(session.player_id, item.main_item.item_id)
            if not raw:
                continue
            # 强化/穿戴等可能已经改变实例，不能用旧临时包快照覆盖库存。
            item.ParseFromString(raw)
            item.pack_type = ItemDetail.PackType.PackType_Inventory
            item.main_item.temp_pack_index = 0
            rsp.items.add().CopyFrom(item)
            rsp1.items.add().CopyFrom(item)
        session.temp_pack.clear()

        session.send(MsgId.TempPackItemStoreRsp, rsp, packet_id)  # 1409,1410
        if rsp1.items:
            session.send(MsgId.PackNotice, rsp1, 0)
