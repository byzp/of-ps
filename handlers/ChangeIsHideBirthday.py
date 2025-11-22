from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeIsHideBirthdayReq_pb2
import proto.OverField_pb2 as ChangeIsHideBirthdayRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeIsHideBirthdayReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeIsHideBirthdayReq_pb2.ChangeIsHideBirthdayReq()
        req.ParseFromString(data)

        rsp = ChangeIsHideBirthdayRsp_pb2.ChangeIsHideBirthdayRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        db.set_players_info(session.player_id, "is_hide_birthday", req.is_hide_birthday)

        session.send(
            CmdId.ChangeIsHideBirthdayRsp, rsp, False, packet_id
        )  # 更改是否隐藏生日 2313 2314
