from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeHideTypeReq_pb2
import proto.OverField_pb2 as ChangeHideTypeRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeHideTypeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHideTypeReq_pb2.ChangeHideTypeReq()
        req.ParseFromString(data)

        rsp = ChangeHideTypeRsp_pb2.ChangeHideTypeRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.hide_value = db.set_hide_type(session.player_id, req.hide_type)

        session.send(
            CmdId.ChangeHideTypeRsp, rsp, False, packet_id
        )  # 更改隐藏类型 2317 2318
