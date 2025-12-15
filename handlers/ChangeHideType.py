from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as ChangeHideTypeReq_pb2
import proto.OverField_pb2 as ChangeHideTypeRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangeHideTypeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHideTypeReq_pb2.ChangeHideTypeReq()
        req.ParseFromString(data)
        rsp = ChangeHideTypeRsp_pb2.ChangeHideTypeRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        current_status = db.get_players_info(
            session.player_id, "hide_value"
        )  # 获取当前状态
        new_status = 0 if current_status else 1

        db.set_players_info(session.player_id, "hide_value", new_status)
        rsp.hide_value = new_status

        session.send(MsgId.ChangeHideTypeRsp, rsp, packet_id)  # 更改隐藏类型 2317 2318
