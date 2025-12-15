from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetWeaponReq_pb2
import proto.OverField_pb2 as GetWeaponRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetWeaponReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetWeaponReq_pb2.GetWeaponReq()
        req.ParseFromString(data)

        rsp = GetWeaponRsp_pb2.GetWeaponRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        item_blobs = db.get_item_detail(session.player_id, table="items_s")

        weapon_count = 0
        for blob in item_blobs:
            try:
                item_detail = pb.ItemDetail()
                item_detail.ParseFromString(blob)
                if item_detail.main_item.item_tag == pb.EBagItemTag_Weapon:
                    rsp.weapons.append(item_detail.main_item.weapon)
                    weapon_count += 1
            except Exception as e:
                logger.error(f"Error parsing item detail: {e}")
                continue

        rsp.total_num = weapon_count
        rsp.end_index = weapon_count

        session.send(MsgId.GetWeaponRsp, rsp, packet_id)  # 获取武器列表 1517 1518
