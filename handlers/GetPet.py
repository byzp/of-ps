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
        for item_b in db.get_item_detail(session.player_id, table="items_s"):
            tmp = ItemDetail()
            tmp.ParseFromString(item_b)
            if tmp.main_item.item_tag == EBagItemTag.EBagItemTag_Pet:
                rsp.pets.add().CopyFrom(tmp.main_item.pet)
                rsp.total_num += 1
        rsp.end_index = req.end_index

        session.send(MsgId.GetPetRsp, rsp, packet_id)
