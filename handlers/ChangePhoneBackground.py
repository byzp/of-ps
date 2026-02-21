from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import ChangePhoneBackgroundReq, ChangePhoneBackgroundRsp, StatusCode

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangePhoneBackgroundReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePhoneBackgroundReq()
        req.ParseFromString(data)

        rsp = ChangePhoneBackgroundRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.phone_background = req.phone_background
        db.set_players_info(session.player_id, "phone_background", req.phone_background)

        session.send(
            MsgId.ChangePhoneBackgroundRsp, rsp, packet_id
        )  # 更换手机背景 1517 1518
