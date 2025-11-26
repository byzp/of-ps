from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangePlayerSexReq_pb2
import proto.OverField_pb2 as ChangePlayerSexRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangePlayerSexReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePlayerSexReq_pb2.ChangePlayerSexReq()
        req.ParseFromString(data)

        rsp = ChangePlayerSexRsp_pb2.ChangePlayerSexRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.sex = req.sex

        db.set_players_info(session.player_id, "sex", req.sex)

        session.send(CmdId.ChangePlayerSexRsp, rsp, packet_id)  # 修改性别 1521 1522
