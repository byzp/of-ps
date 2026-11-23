from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import GetExpressAddressReq, GetExpressAddressRsp, StatusCode

import server.photo_share as ps


@packet_handler(MsgId.GetExpressAddressReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetExpressAddressReq()
        req.ParseFromString(data)

        rsp = GetExpressAddressRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 实物奖品收货地址(经 photo_share 快照持久化), 内存态回显
        with ps.lock_express:
            record = ps.express_address.get(session.player_id)
            if record:
                rsp.name = record["name"]
                rsp.phone = record["phone"]
                rsp.address = record["address"]
                rsp.order_no = record["order_no"]
                for item_id, num in record["items"]:
                    item = rsp.items.add()
                    item.item_id = item_id
                    item.num = num

        session.send(MsgId.GetExpressAddressRsp, rsp, packet_id)  # 2571,2572
