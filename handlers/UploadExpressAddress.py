from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

from proto.net_pb2 import UploadExpressAddressReq, UploadExpressAddressRsp, StatusCode

import server.photo_share as ps

logger = logging.getLogger(__name__)


@packet_handler(MsgId.UploadExpressAddressReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UploadExpressAddressReq()
        req.ParseFromString(data)

        rsp = UploadExpressAddressRsp()
        rsp.status = StatusCode.StatusCode_OK

        order_no = f"{session.player_id}{int(time.time())}"
        with ps.lock_express:
            ps.express_address[session.player_id] = {
                "name": req.name,
                "phone": req.phone,
                "address": req.address,
                "items": [(item.item_id, item.num) for item in req.items],
                "order_no": order_no,
            }
        logger.info(
            "玩家上传收货地址 player=%s name=%s phone=%s address=%s order_no=%s",
            session.player_id,
            req.name,
            req.phone,
            req.address,
            order_no,
        )

        rsp.order_no = order_no
        for item in req.items:
            rsp.items.add().CopyFrom(item)
        session.send(MsgId.UploadExpressAddressRsp, rsp, packet_id)  # 2573,2574
