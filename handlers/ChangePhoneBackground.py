from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangePhoneBackgroundReq_pb2
import proto.OverField_pb2 as ChangePhoneBackgroundRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangePhoneBackgroundReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePhoneBackgroundReq_pb2.ChangePhoneBackgroundReq()
        req.ParseFromString(data)

        rsp = ChangePhoneBackgroundRsp_pb2.ChangePhoneBackgroundRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.phone_background = req.phone_background
        db.set_players_info(session.player_id, "phone_background", req.phone_background)

        session.send(
            CmdId.ChangePhoneBackgroundRsp, rsp, packet_id
        )  # 更换手机背景 1517 1518
