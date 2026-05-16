from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PetRenameReq,
    PetRenameRsp,
    PackNotice,
    StatusCode,
)

import utils.db as db


@packet_handler(MsgId.PetRenameReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PetRenameReq()
        req.ParseFromString(data)

        rsp = PetRenameRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.pet_instance_id = req.pet_instance_id
        rsp.name = req.name
        pet_b = db.get_item_detail(session.player_id, None, req.pet_instance_id)
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        tmp = rsp1.items.add()
        tmp.ParseFromString(pet_b)
        tmp.main_item.pet.name = req.name
        db.set_item_detail(
            session.player_id,
            tmp.SerializeToString(),
            None,
            tmp.main_item.pet.instance_id,
        )
        session.send(MsgId.PackNotice, rsp1, 0)
        session.send(MsgId.PetRenameRsp, rsp, packet_id)
