from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import ChangePlayerSexReq, ChangePlayerSexRsp, StatusCode

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangePlayerSexReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePlayerSexReq()
        req.ParseFromString(data)

        rsp = ChangePlayerSexRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.sex = req.sex

        db.set_players_info(session.player_id, "sex", req.sex)

        session.send(MsgId.ChangePlayerSexRsp, rsp, packet_id)  # 修改性别 1521 1522
