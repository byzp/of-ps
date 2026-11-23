from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityUploadWishTxtReq,
    ActivityUploadWishTxtRsp,
    StatusCode,
)

import utils.db as db

"""
# 活动上传许愿文本 4515 4516
"""


@packet_handler(MsgId.ActivityUploadWishTxtReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityUploadWishTxtReq()
        req.ParseFromString(data)

        rsp = ActivityUploadWishTxtRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.txt = req.txt
        rsp.activity_id = req.activity_id
        # 许愿文本持久化于 kv(ns=wish_txt)
        db.set_kv(
            session.player_id,
            "wish_txt",
            str(req.activity_id),
            req.txt.encode(),
        )

        session.send(MsgId.ActivityUploadWishTxtRsp, rsp, packet_id)  # 4515,4516
