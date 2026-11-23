from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ArmorStrengthReq,
    ArmorStrengthRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils import item_mgr
from utils import achieve_track


def _strengthen_groups(armor):
    """强化配置链: Armor.json armor.armor_property_i_d
    -> armor_property.armor_property_group_info(按 property_index,
       兜底按防具 level 落在 [min_level, max_level] 区间)
    -> group.strengthen_i_d -> armor_strengthen.armor_strengthen_group_info
    返回各强化等级条目 tuple({level, armor_strength_need_item, ...}), 失败 None"""
    armor_res = res.get("Armor", {})
    cfg = None
    for e in armor_res.get("armor", {}).get("datas", ()):
        if e.get("i_d") == armor.armor_id or e.get("item_i_d") == armor.armor_id:
            cfg = e
            break
    if not cfg:
        return None
    prop = None
    for e in armor_res.get("armor_property", {}).get("datas", ()):
        if e.get("i_d") == cfg.get("armor_property_i_d"):
            prop = e
            break
    if not prop:
        return None
    groups = prop.get("armor_property_group_info", ())
    group = None
    if 1 <= armor.property_index <= len(groups):
        group = groups[armor.property_index - 1]  # make_item 写入的 1 基索引
    else:
        for g in groups:
            if g.get("min_level", 0) <= armor.level <= g.get("max_level", 0):
                group = g
                break
    if not group or not group.get("strengthen_i_d"):
        return None
    for e in armor_res.get("armor_strengthen", {}).get("datas", ()):
        if e.get("i_d") == group["strengthen_i_d"]:
            return e.get("armor_strengthen_group_info", ())
    return None


@packet_handler(MsgId.ArmorStrengthReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ArmorStrengthReq()
        req.ParseFromString(data)

        rsp = ArmorStrengthRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.armor_instance_id = req.armor_instance_id

        if not req.armor_instance_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ArmorStrengthRsp, rsp, packet_id)
            return
        blob = db.get_item_detail(session.player_id, None, req.armor_instance_id)
        if not blob:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ArmorStrengthRsp, rsp, packet_id)
            return
        item = ItemDetail()
        item.ParseFromString(blob)
        armor = item.main_item.armor

        groups = _strengthen_groups(armor)
        if groups is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ArmorStrengthRsp, rsp, packet_id)
            return

        # 目标等级条目; 无下一级条目 = 已到该防具等级段的强化上限
        target = armor.strength_level + 1
        entry = None
        for g in groups:
            if g.get("level") == target:
                entry = g
                break
        if entry is None:
            rsp.status = StatusCode.StatusCode_ARMOR_MAX_STRENGTH_LEVEL
            rsp.strength_level = armor.strength_level
            session.send(MsgId.ArmorStrengthRsp, rsp, packet_id)
            return

        # 强化材料消耗: armor_strengthen_group_info.armor_strength_need_item
        # 先整体校验再扣除, 不足直接失败
        needs = [
            (n.get("need_item_i_d", 0), n.get("need_item_count", 0))
            for n in entry.get("armor_strength_need_item", ())
            if n.get("need_item_i_d") and n.get("need_item_count")
        ]
        for need_id, need_num in needs:
            if item_mgr.get_num(session.player_id, need_id) < need_num:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.ArmorStrengthRsp, rsp, packet_id)
                return

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        if needs and not item_mgr.consume_items(
            session.player_id, needs, pack_notice=rsp1, session=session
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.ArmorStrengthRsp, rsp, packet_id)
            return

        # 属性加成(add_ext_hp 等)由客户端按 strength_level 查表显示, 服务器不改数值
        armor.strength_level = target
        armor.strength_exp = 0
        db.set_item_detail(
            session.player_id, item.SerializeToString(), None, req.armor_instance_id
        )
        rsp.strength_level = armor.strength_level
        rsp1.items.add().CopyFrom(item)

        # 成就: 装备强化 + 防具升星(事件层归族)
        achieve_track.report(session, "armor_enhance")
        session.send(MsgId.ArmorStrengthRsp, rsp, packet_id)  # 1963,1964
        session.send(MsgId.PackNotice, rsp1, 0)
