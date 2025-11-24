from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as GetArmorReq_pb2
import proto.OverField_pb2 as GetArmorRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GetArmorReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetArmorReq_pb2.GetArmorReq()
        req.ParseFromString(data)

        rsp = GetArmorRsp_pb2.GetArmorRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        max_num = req.end_index - req.start_index
        total_num = 0

        for item in db.get_item_detail(session.player_id):
            tmp = pb.ItemDetail()
            tmp.ParseFromString(item)
            if tmp.main_item.item_tag == pb.EBagItemTag_Armor:
                # if tmp.main_item.armor.armor_id >2331000:
                if max_num == total_num:
                    break
                total_num += 1
                rsp.armors.add().CopyFrom(tmp.main_item.armor)

        rsp.total_num = total_num
        rsp.end_index = req.start_index + total_num

        session.send(CmdId.GetArmorRsp, rsp, packet_id)  # 获取防具列表 1403 1404
