from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    WeaponStrengthReq,
    WeaponStrengthRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils import item_mgr
from utils import achieve_track


def _strengthen_groups(weapon):
    """强化配置链: Weapon.json weapon.weapon_property_i_d
    -> weapon_property.weapon_property_group_info(按 property_index,
       兜底按武器 level 落在 [min_level, max_level] 区间)
    -> group.strengthen_i_d -> weapon_strengthen.weapon_strengthen_group_info
    返回各强化等级条目 tuple({level, add_attack, weapon_strength_need_item}), 失败 None"""
    weapon_res = res.get("Weapon", {})
    cfg = None
    for e in weapon_res.get("weapon", {}).get("datas", ()):
        if e.get("i_d") == weapon.weapon_id or e.get("item_i_d") == weapon.weapon_id:
            cfg = e
            break
    if not cfg:
        return None
    prop = None
    for e in weapon_res.get("weapon_property", {}).get("datas", ()):
        if e.get("i_d") == cfg.get("weapon_property_i_d"):
            prop = e
            break
    if not prop:
        return None
    groups = prop.get("weapon_property_group_info", ())
    group = None
    if 1 <= weapon.property_index <= len(groups):
        group = groups[weapon.property_index - 1]  # make_item 写入的 1 基索引
    else:
        for g in groups:
            if g.get("min_level", 0) <= weapon.level <= g.get("max_level", 0):
                group = g
                break
    if not group or not group.get("strengthen_i_d"):
        return None
    for e in weapon_res.get("weapon_strengthen", {}).get("datas", ()):
        if e.get("i_d") == group["strengthen_i_d"]:
            return e.get("weapon_strengthen_group_info", ())
    return None


@packet_handler(MsgId.WeaponStrengthReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WeaponStrengthReq()
        req.ParseFromString(data)

        rsp = WeaponStrengthRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.weapon_instance_id = req.weapon_instance_id

        if not req.weapon_instance_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
            return
        blob = db.get_item_detail(session.player_id, None, req.weapon_instance_id)
        if not blob:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
            return
        item = ItemDetail()
        item.ParseFromString(blob)
        weapon = item.main_item.weapon

        groups = _strengthen_groups(weapon)
        if groups is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
            return

        # 目标等级条目; 无下一级条目 = 已到该武器等级段的强化上限
        target = weapon.strength_level + 1
        entry = None
        for g in groups:
            if g.get("level") == target:
                entry = g
                break
        if entry is None:
            rsp.status = StatusCode.StatusCode_WEAPON_MAX_STRENGTH_LEVEL
            rsp.strength_level = weapon.strength_level
            session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
            return

        # 强化材料消耗: weapon_strengthen_group_info.weapon_strength_need_item
        # 先整体校验再扣除, 不足直接失败
        needs = [
            (n.get("need_item_i_d", 0), n.get("need_item_count", 0))
            for n in entry.get("weapon_strength_need_item", ())
            if n.get("need_item_i_d") and n.get("need_item_count")
        ]
        for need_id, need_num in needs:
            if item_mgr.get_num(session.player_id, need_id) < need_num:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
                return

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        if needs and not item_mgr.consume_items(
            session.player_id, needs, pack_notice=rsp1, session=session
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
            return

        # 属性加成(add_attack)由客户端按 strength_level 查表显示, 服务器不改 attack
        weapon.strength_level = target
        weapon.strength_exp = 0
        db.set_item_detail(
            session.player_id, item.SerializeToString(), None, req.weapon_instance_id
        )
        rsp.strength_level = weapon.strength_level
        rsp1.items.add().CopyFrom(item)

        achieve_track.report(session, "weapon_enhance")
        session.send(MsgId.WeaponStrengthRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
