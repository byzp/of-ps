from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import ChangeHeadReq, ChangeHeadRsp, StatusCode

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangeHeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHeadReq()
        req.ParseFromString(data)

        rsp = ChangeHeadRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.head = req.head

        session.avatar_id = req.head
        db.set_players_info(session.player_id, "head", session.avatar_id)

        session.send(MsgId.ChangeHeadRsp, rsp, packet_id)  # 更换头像 1528 1529
