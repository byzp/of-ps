from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import GetArmorReq, GetArmorRsp, StatusCode, ItemDetail, EBagItemTag

import utils.db as db


@packet_handler(MsgId.GetArmorReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetArmorReq()
        req.ParseFromString(data)

        rsp = GetArmorRsp()
        rsp.status = StatusCode.StatusCode_OK

        all_armors = []
        for item in db.get_item_detail(session.player_id, table="items_s"):
            tmp = ItemDetail()
            tmp.ParseFromString(item)
            if tmp.main_item.item_tag == EBagItemTag.EBagItemTag_Armor:
                all_armors.append(tmp.main_item.armor)
        rsp.total_num = len(all_armors)
        start = req.start_index if req.start_index else 0
        end = req.end_index if req.end_index else len(all_armors)
        for a in all_armors[start:end]:
            rsp.armors.add().CopyFrom(a)
        rsp.end_index = min(end, len(all_armors))

        session.send(MsgId.GetArmorRsp, rsp, packet_id)  # 获取防具列表 1403 1404
