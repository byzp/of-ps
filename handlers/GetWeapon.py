from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetWeaponReq_pb2
import proto.OverField_pb2 as GetWeaponRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GetWeaponReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetWeaponReq_pb2.GetWeaponReq()
        req.ParseFromString(data)

        rsp = GetWeaponRsp_pb2.GetWeaponRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        max_num = req.end_index - req.start_index
        total_num = 0

        for item in db.get_item_detail(session.player_id):
            tmp = pb.ItemDetail()
            tmp.ParseFromString(item)
            if tmp.main_item.item_tag == pb.EBagItemTag_Weapon:
                if (
                    tmp.main_item.weapon.weapon_id > 1019000
                ):  # 鱼竿之类的物品会导致加载异常
                    if max_num == total_num:
                        break
                    total_num += 1
                    rsp.weapons.add().CopyFrom(tmp.main_item.weapon)

        rsp.total_num = total_num
        rsp.end_index = req.start_index + total_num

        session.send(
            CmdId.GetWeaponRsp, rsp, False, packet_id
        )  # 获取武器列表 1517 1518
