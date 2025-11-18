from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeHeadReq_pb2
import proto.OverField_pb2 as ChangeHeadRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeHeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHeadReq_pb2.ChangeHeadReq()
        req.ParseFromString(data)

        rsp = ChangeHeadRsp_pb2.ChangeHeadRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.head = req.head

        session.avatar_id = req.head
        db.set_avatar(session.player_id, req.session.avatar_id)

        session.send(CmdId.ChangeHeadRsp, rsp, False, packet_id)  # 更换头像 1528 1529
