from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GetPetReq, GetPetRsp, StatusCode, ItemDetail, EBagItemTag

import utils.db as db


@packet_handler(MsgId.GetPetReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetPetReq()
        req.ParseFromString(data)

        rsp = GetPetRsp()
        rsp.status = StatusCode.StatusCode_OK
        all_pets = []
        for item_b in db.get_item_detail(session.player_id, table="items_s"):
            tmp = ItemDetail()
            tmp.ParseFromString(item_b)
            if tmp.main_item.item_tag == EBagItemTag.EBagItemTag_Pet:
                all_pets.append(tmp.main_item.pet)
        rsp.total_num = len(all_pets)
        start = max(0, req.start_index) if req.start_index else 0
        end = req.end_index if req.end_index else len(all_pets)
        for p in all_pets[start:end]:
            rsp.pets.add().CopyFrom(p)
        rsp.end_index = min(end, len(all_pets))

        session.send(MsgId.GetPetRsp, rsp, packet_id)
