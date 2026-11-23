from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import PhotoShareDetailReq, PhotoShareDetailRsp, StatusCode

import server.photo_share as ps
import utils.db as db


@packet_handler(MsgId.PhotoShareDetailReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PhotoShareDetailReq()
        req.ParseFromString(data)

        rsp = PhotoShareDetailRsp()

        with ps.lock_photo:
            record = ps.photos.get(req.code)
            if not record:
                rsp.status = StatusCode.StatusCode_PS_NOT_EXIST
                session.send(MsgId.PhotoShareDetailRsp, rsp, packet_id)
                return
            rsp.status = StatusCode.StatusCode_OK
            ps.fill_detail(rsp.info, record, session.player_id)

        session.send(MsgId.PhotoShareDetailRsp, rsp, packet_id)  # 2557,2558
