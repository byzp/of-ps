import random

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    EquipDisassembleReq,
    EquipDisassembleRsp,
    StatusCode,
    ItemDetail,
)

import utils.db as db
from utils.res_loader import res
from utils import item_mgr, achieve_track


def _rows(table, name):
    if not isinstance(table, dict):
        return ()
    section = table.get(name)
    if not isinstance(section, dict):
        return ()
    rows = section.get("datas")
    if not isinstance(rows, (list, tuple)):
        return ()
    return tuple(row for row in rows if isinstance(row, dict))


def _disassemble_row(equip, kind):
    table = res.get(kind.capitalize())
    equip_id = getattr(equip, f"{kind}_id")
    cfg = next(
        (
            row
            for row in _rows(table, kind)
            if row.get("i_d") == equip_id or row.get("item_i_d") == equip_id
        ),
        None,
    )
    if not cfg or not cfg.get(f"{kind}_property_i_d"):
        return None
    prop = next(
        (
            row
            for row in _rows(table, f"{kind}_property")
            if row.get("i_d") == cfg[f"{kind}_property_i_d"]
        ),
        None,
    )
    if not prop:
        return None
    groups = prop.get(f"{kind}_property_group_info")
    if not isinstance(groups, (list, tuple)):
        return None
    if 1 <= equip.property_index <= len(groups):
        group = groups[equip.property_index - 1]
    else:
        group = next(
            (
                g
                for g in groups
                if isinstance(g, dict)
                and g.get("min_level", 0) <= equip.level <= g.get("max_level", 0)
            ),
            None,
        )
    if not isinstance(group, dict) or not group.get("disassemble_i_d"):
        return None
    return next(
        (
            row
            for row in _rows(table, f"{kind}_disassemble")
            if row.get("i_d") == group["disassemble_i_d"]
        ),
        None,
    )


@packet_handler(MsgId.EquipDisassembleReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = EquipDisassembleReq()
        req.ParseFromString(data)
        rsp = EquipDisassembleRsp(status=StatusCode.StatusCode_OK)
        grant_list = []
        removed = set()
        pending = []
        for kind, ids, rsp_ids in (
            ("weapon", req.weapon_ids, rsp.weapon_ids),
            ("armor", req.armor_ids, rsp.armor_ids),
        ):
            for instance_id in ids:
                if instance_id in removed:
                    continue
                blob = db.get_item_detail(session.player_id, None, instance_id)
                if not blob:
                    continue
                item = ItemDetail()
                item.ParseFromString(blob)
                if not item.main_item.HasField(kind):
                    continue
                equip = getattr(item.main_item, kind)
                if equip.is_lock or equip.wearer_id:
                    continue
                row = _disassemble_row(equip, kind)
                if row is None:
                    continue
                rewards = row.get(f"{kind}_disassemble_item")
                if not isinstance(rewards, (list, tuple)) or not rewards:
                    continue
                if any(
                    not isinstance(it, dict) or not it.get("item_i_d") for it in rewards
                ):
                    continue
                for it in rewards:
                    rate = float(it.get("item_rate", 1))
                    lo = int(it.get("item_min_count", 1))
                    hi = int(it.get("item_max_count", lo))
                    item_id = int(it["item_i_d"])
                    if random.random() < rate:
                        grant_list.append((item_id, random.randint(lo, hi)))
                removed.add(instance_id)
                pending.append(instance_id)
                rsp_ids.append(instance_id)
        for instance_id in pending:
            db.del_item_detail(session.player_id, instance_id)
        if grant_list:
            item_mgr.grant_items(
                session.player_id,
                grant_list,
                session=session,
                rsp_items=rsp.items,
            )
        if rsp.weapon_ids or rsp.armor_ids:
            achieve_track.report(
                session,
                "disassemble",
                armor_n=len(rsp.armor_ids),
                weapon_n=len(rsp.weapon_ids),
            )
        session.send(MsgId.EquipDisassembleRsp, rsp, packet_id)
