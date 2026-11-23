from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    GetWeaponReq,
    GetWeaponRsp,
    StatusCode,
    ItemDetail,
    EBagItemTag,
)

import utils.db as db
from utils.res_loader import res

_weapon_sys = None


def _weapon_system(weapon_id):
    """Weapon.json weapon{i_d}.new_weapon_system_type(EWeaponSystemType)"""
    global _weapon_sys
    if _weapon_sys is None:
        _weapon_sys = {
            e.get("i_d"): e.get("new_weapon_system_type", 0)
            for e in res.get("Weapon", {}).get("weapon", {}).get("datas", ())
        }
    return _weapon_sys.get(weapon_id, 0)


@packet_handler(MsgId.GetWeaponReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetWeaponReq()
        req.ParseFromString(data)

        rsp = GetWeaponRsp()
        rsp.status = StatusCode.StatusCode_OK

        item_blobs = db.get_item_detail(session.player_id, table="items_s")
        all_weapons = []
        for blob in item_blobs:
            item_detail = ItemDetail()
            item_detail.ParseFromString(blob)
            if item_detail.main_item.item_tag != EBagItemTag.EBagItemTag_Weapon:
                continue
            if req.weapon_system_type:
                _sys = _weapon_system(item_detail.main_item.weapon.weapon_id)
                if _sys != req.weapon_system_type:
                    continue
            all_weapons.append(item_detail.main_item.weapon)
        rsp.total_num = len(all_weapons)
        # 分页窗口 [start_index, end_index); 0 界限视为全量
        start = max(0, req.start_index) if req.start_index else 0
        end = req.end_index if req.end_index else len(all_weapons)
        for w in all_weapons[start:end]:
            rsp.weapons.add().CopyFrom(w)
        rsp.end_index = min(end, len(all_weapons))

        session.send(MsgId.GetWeaponRsp, rsp, packet_id)  # 获取武器列表 1517 1518
