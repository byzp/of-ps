from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangePhotoShareTitleReq, ChangePhotoShareTitleRsp, StatusCode

import server.photo_share as ps
import utils.db as db


@packet_handler(MsgId.ChangePhotoShareTitleReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePhotoShareTitleReq()
        req.ParseFromString(data)

        rsp = ChangePhotoShareTitleRsp()

        with ps.lock_photo:
            record = ps.photos.get(req.code)
            if not record or record["player_id"] != session.player_id:
                rsp.status = StatusCode.StatusCode_PS_NOT_EXIST
                session.send(MsgId.ChangePhotoShareTitleRsp, rsp, packet_id)
                return
            record["title"] = req.title
            record["tag1"] = req.tag1
            record["tag2"] = req.tag2

        rsp.status = StatusCode.StatusCode_OK
        rsp.title = req.title
        rsp.tag1 = req.tag1
        rsp.tag2 = req.tag2
        session.send(MsgId.ChangePhotoShareTitleRsp, rsp, packet_id)  # 2553,2554
