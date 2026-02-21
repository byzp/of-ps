from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GetArmorReq, GetArmorRsp, StatusCode, ItemDetail, EBagItemTag

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetArmorReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetArmorReq()
        req.ParseFromString(data)

        rsp = GetArmorRsp()
        rsp.status = StatusCode.StatusCode_OK

        max_num = req.end_index - req.start_index
        total_num = 0

        for item in db.get_item_detail(session.player_id):
            tmp = ItemDetail()
            tmp.ParseFromString(item)
            if tmp.main_item.item_tag == EBagItemTag.EBagItemTag_Armor:
                # if tmp.main_item.armor.armor_id >2331000:
                if max_num == total_num:
                    break
                total_num += 1
                rsp.armors.add().CopyFrom(tmp.main_item.armor)

        rsp.total_num = total_num
        rsp.end_index = req.start_index + total_num

        session.send(MsgId.GetArmorRsp, rsp, packet_id)  # 获取防具列表 1403 1404
