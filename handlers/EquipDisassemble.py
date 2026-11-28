import math
import random

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import EquipDisassembleReq, EquipDisassembleRsp, StatusCode

from server import character_growth as growth
from utils import achieve_track, item_mgr
import utils.db as db


def _rewards(kind, equip):
    row = growth.disassemble_row(kind, equip)
    entries = row.get(f"{kind}_disassemble_item", ())
    if not isinstance(entries, (list, tuple)) or not entries:
        return None
    parsed = []
    for entry in entries:
        if not isinstance(entry, dict):
            return None
        item_id = int(entry.get("item_i_d", 0) or 0)
        rate = float(entry.get("item_rate", 1) or 0)
        low = int(entry.get("item_min_count", 1) or 0)
        high = int(entry.get("item_max_count", low) or 0)
        if (
            growth.item_config(item_id) is None
            or not math.isfinite(rate)
            or not 0 <= rate <= 1
            or low <= 0
            or high < low
        ):
            return None
        parsed.append((item_id, rate, low, high))
    return parsed


@packet_handler(MsgId.EquipDisassembleReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = EquipDisassembleReq()
        req.ParseFromString(data)
        rsp = EquipDisassembleRsp(status=StatusCode.StatusCode_OK)
        try:
            with growth.transaction(session.player_id):
                seen = set()
                pending = []
                grant_list = []
                for kind, ids, response_ids in (
                    ("weapon", req.weapon_ids, rsp.weapon_ids),
                    ("armor", req.armor_ids, rsp.armor_ids),
                ):
                    for instance_id in ids:
                        if not instance_id or instance_id in seen:
                            continue
                        seen.add(instance_id)
                        try:
                            detail = growth.load_owned_instance(
                                session.player_id, instance_id, kind
                            )
                            equip = getattr(detail.main_item, kind)
                            if equip.is_lock or equip.wearer_id:
                                continue
                            if kind == "weapon" and equip.inscription1:
                                continue
                            rewards = _rewards(kind, equip)
                            if rewards is None:
                                continue
                        except growth.GrowthError:
                            # 批量分解保留跳过非法项语义；已接受项仍在同一事务内。
                            continue
                        for item_id, rate, low, high in rewards:
                            if random.random() < rate:
                                grant_list.append((item_id, random.randint(low, high)))
                        pending.append(instance_id)
                        response_ids.append(instance_id)
                for instance_id in pending:
                    db.del_item_detail(session.player_id, instance_id)
                if grant_list:
                    item_mgr.grant_items(
                        session.player_id, grant_list, rsp_items=rsp.items, session=None
                    )
        except growth.GrowthError as error:
            rsp.status = error.status
            session.send(MsgId.EquipDisassembleRsp, rsp, packet_id)
            return

        if rsp.weapon_ids or rsp.armor_ids:
            achieve_track.report(
                session,
                "disassemble",
                armor_n=len(rsp.armor_ids),
                weapon_n=len(rsp.weapon_ids),
            )
        session.send(MsgId.EquipDisassembleRsp, rsp, packet_id)
