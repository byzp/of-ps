from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    WeaponInscriptionRemoveReq,
    WeaponInscriptionRemoveRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

import utils.db as db


@packet_handler(MsgId.WeaponInscriptionRemoveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WeaponInscriptionRemoveReq()
        req.ParseFromString(data)

        rsp = WeaponInscriptionRemoveRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.weapon_instance_id = req.weapon_instance_id

        if not req.weapon_instance_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.WeaponInscriptionRemoveRsp, rsp, packet_id)
            return
        weapon_b = db.get_item_detail(session.player_id, None, req.weapon_instance_id)
        if not weapon_b:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.WeaponInscriptionRemoveRsp, rsp, packet_id)
            return
        weapon_item = ItemDetail()
        weapon_item.ParseFromString(weapon_b)

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        old_id = weapon_item.main_item.weapon.inscription1
        weapon_item.main_item.weapon.inscription1 = 0
        db.set_item_detail(
            session.player_id,
            weapon_item.SerializeToString(),
            None,
            req.weapon_instance_id,
        )
        rsp1.items.add().CopyFrom(weapon_item)

        # 铭刻物品解除绑定
        if old_id:
            ins_b = db.get_item_detail(session.player_id, old_id)
            if ins_b:
                ins_item = ItemDetail()
                ins_item.ParseFromString(ins_b)
                ins_item.main_item.inscription.weapon_instance_id = 0
                db.set_item_detail(
                    session.player_id, ins_item.SerializeToString(), old_id
                )
                rsp1.items.add().CopyFrom(ins_item)

        session.send(MsgId.WeaponInscriptionRemoveRsp, rsp, packet_id)  # 1703,1704
        session.send(MsgId.PackNotice, rsp1, 0)
