from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    WeaponInscriptionInlaidReq,
    WeaponInscriptionInlaidRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils import item_mgr


@packet_handler(MsgId.WeaponInscriptionInlaidReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WeaponInscriptionInlaidReq()
        req.ParseFromString(data)

        rsp = WeaponInscriptionInlaidRsp()
        rsp.status = StatusCode.StatusCode_OK

        if not req.weapon_instance_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.WeaponInscriptionInlaidRsp, rsp, packet_id)
            return
        weapon_b = db.get_item_detail(session.player_id, None, req.weapon_instance_id)
        if not weapon_b:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.WeaponInscriptionInlaidRsp, rsp, packet_id)
            return
        weapon_item = ItemDetail()
        weapon_item.ParseFromString(weapon_b)

        # 归属校验: 玩家必须拥有该铭刻(铭刻按 item_id 存于 items 表, 见 pb_create.make_item)
        ins_b = db.get_item_detail(session.player_id, req.inscription_id)
        if not ins_b:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.WeaponInscriptionInlaidRsp, rsp, packet_id)
            return
        ins_item = ItemDetail()
        ins_item.ParseFromString(ins_b)

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        # 目标武器上的旧铭刻解除绑定
        old_id = weapon_item.main_item.weapon.inscription1
        if old_id and old_id != req.inscription_id:
            old_b = db.get_item_detail(session.player_id, old_id)
            if old_b:
                old_item = ItemDetail()
                old_item.ParseFromString(old_b)
                old_item.main_item.inscription.weapon_instance_id = 0
                db.set_item_detail(
                    session.player_id, old_item.SerializeToString(), old_id
                )
                rsp.inscriptions.add().CopyFrom(old_item.main_item.inscription)
                rsp.items.add().CopyFrom(old_item)
                rsp1.items.add().CopyFrom(old_item)

        # 该铭刻若已镶在别的武器上, 先清空旧宿主武器的铭刻槽(一铭刻一武器)
        prev_weapon_id = ins_item.main_item.inscription.weapon_instance_id
        if prev_weapon_id and prev_weapon_id != req.weapon_instance_id:
            prev_b = db.get_item_detail(session.player_id, None, prev_weapon_id)
            if prev_b:
                prev_item = ItemDetail()
                prev_item.ParseFromString(prev_b)
                prev_item.main_item.weapon.inscription1 = 0
                db.set_item_detail(
                    session.player_id,
                    prev_item.SerializeToString(),
                    None,
                    prev_weapon_id,
                )
                rsp.weapon_instances.add().CopyFrom(prev_item.main_item.weapon)
                rsp.items.add().CopyFrom(prev_item)
                rsp1.items.add().CopyFrom(prev_item)

        # 镶嵌消耗(Inscription.inscription level=1: 金币 + 材料), 未配置则免耗
        _cfg = next(
            (
                c
                for c in res.get("Inscription", {})
                .get("inscription", {})
                .get("datas", [])
                if c.get("item_i_d") == req.inscription_id
            ),
            None,
        )
        _lv1 = next(
            (
                g
                for g in (_cfg or {}).get("inscription_group_info", ()) or ()
                if int(g.get("level", 0)) == 1
            ),
            None,
        )
        rsp2 = PackNotice()
        rsp2.status = StatusCode.StatusCode_OK
        if _lv1:
            _needs = [(101, int(_lv1.get("need_gold_count", 0)))]
            for ni in _lv1.get("inscription_need_item", ()) or ():
                _needs.append(
                    (int(ni.get("need_item_i_d", 0)), int(ni.get("item_count", 0)))
                )
            item_mgr.consume_items(
                session.player_id,
                [x for x in _needs if x[0]],
                pack_notice=rsp2,
                session=session,
            )

        # 武器记录铭刻
        weapon_item.main_item.weapon.inscription1 = req.inscription_id
        db.set_item_detail(
            session.player_id,
            weapon_item.SerializeToString(),
            None,
            req.weapon_instance_id,
        )
        rsp.weapon_instances.add().CopyFrom(weapon_item.main_item.weapon)
        rsp.items.add().CopyFrom(weapon_item)
        rsp1.items.add().CopyFrom(weapon_item)

        # 铭刻物品记录所镶嵌武器
        ins_item.main_item.inscription.inscription_id = req.inscription_id
        ins_item.main_item.inscription.weapon_instance_id = req.weapon_instance_id
        db.set_item_detail(
            session.player_id, ins_item.SerializeToString(), req.inscription_id
        )
        rsp.inscriptions.add().CopyFrom(ins_item.main_item.inscription)
        rsp.items.add().CopyFrom(ins_item)
        rsp1.items.add().CopyFrom(ins_item)

        session.send(MsgId.WeaponInscriptionInlaidRsp, rsp, packet_id)  # 1701,1702
        session.send(MsgId.PackNotice, rsp1, 0)
        if _lv1:
            session.send(MsgId.PackNotice, rsp2, 0)
