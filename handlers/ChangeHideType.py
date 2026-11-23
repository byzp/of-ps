from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangeHideTypeReq, ChangeHideTypeRsp, StatusCode

import utils.db as db


@packet_handler(MsgId.ChangeHideTypeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHideTypeReq()
        req.ParseFromString(data)
        rsp = ChangeHideTypeRsp()
        rsp.status = StatusCode.StatusCode_OK

        # hide_value 为位图: bit0=账号在线 bit1=签名 bit2=深渊排名(HideType)
        current_status = int(
            db.get_players_info(session.player_id, "hide_value")[0] or 0
        )
        bit = int(req.hide_type) if req.hide_type else 1
        new_status = current_status ^ bit

        db.set_players_info(session.player_id, "hide_value", new_status)
        rsp.hide_value = new_status

        session.send(MsgId.ChangeHideTypeRsp, rsp, packet_id)  # 更改隐藏类型 2317 2318
