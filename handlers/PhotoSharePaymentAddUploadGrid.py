from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PhotoSharePaymentAddUploadGridReq,
    PhotoSharePaymentAddUploadGridRsp,
    StatusCode,
)

import server.photo_share as ps
import utils.db as db


@packet_handler(MsgId.PhotoSharePaymentAddUploadGridReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PhotoSharePaymentAddUploadGridReq()
        req.ParseFromString(data)

        rsp = PhotoSharePaymentAddUploadGridRsp()
        rsp.status = StatusCode.StatusCode_OK

        with ps.lock_photo:
            ps.extra_upload_grid[session.player_id] = (
                ps.extra_upload_grid.get(session.player_id, 0) + 5
            )

        session.send(
            MsgId.PhotoSharePaymentAddUploadGridRsp, rsp, packet_id
        )  # 2563,2564
