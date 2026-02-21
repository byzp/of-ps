from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import ChangeSignReq, ChangeSignRsp, StatusCode

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangeSignReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeSignReq()
        req.ParseFromString(data)

        rsp = ChangeSignRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.sign = req.sign
        db.set_players_info(session.player_id, "sign", req.sign)

        session.send(MsgId.ChangeSignRsp, rsp, packet_id)  # 修改签名 1526 1527
