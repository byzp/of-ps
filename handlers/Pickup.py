from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import PickupReq, PickupRsp, PackNotice, StatusCode

import utils.db as db


@packet_handler(MsgId.PickupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PickupReq()
        req.ParseFromString(data)

        rsp = PickupRsp()
        rsp.status = StatusCode.StatusCode_OK
        item_tup = session.drop_items[req.drop_item_index]
        rsp.items.add().CopyFrom(item_tup[1])

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        rsp1.items.add().CopyFrom(item_tup[1])

        db.set_item_detail(
            session.player_id, item_tup[1].SerializeToString(), None, item_tup[0]
        )

        session.send(MsgId.PickupRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
