from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    LockEquipReq,
    LockEquipRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

import utils.db as db


@packet_handler(MsgId.LockEquipReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = LockEquipReq()
        req.ParseFromString(data)

        rsp = LockEquipRsp()
        rsp.status = StatusCode.StatusCode_OK

        if not req.instance_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.LockEquipRsp, rsp, packet_id)
            return
        blob = db.get_item_detail(session.player_id, None, req.instance_id)
        if not blob:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.LockEquipRsp, rsp, packet_id)
            return
        item = ItemDetail()
        item.ParseFromString(blob)

        # 无目标状态字段, 视为切换锁定状态
        # 不信任 req.equip_type: 按物品实际 oneof 分支判定,
        kind = item.main_item.WhichOneof("item")
        if kind == "weapon":
            item.main_item.weapon.is_lock = not item.main_item.weapon.is_lock
        elif kind == "armor":
            item.main_item.armor.is_lock = not item.main_item.armor.is_lock
        else:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.LockEquipRsp, rsp, packet_id)
            return
        db.set_item_detail(
            session.player_id, item.SerializeToString(), None, req.instance_id
        )

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        rsp1.items.add().CopyFrom(item)

        session.send(MsgId.LockEquipRsp, rsp, packet_id)  # 1427,1428
        session.send(MsgId.PackNotice, rsp1, 0)
