from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import ChangeIsHideBirthdayReq, ChangeIsHideBirthdayRsp, StatusCode

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ChangeIsHideBirthdayReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeIsHideBirthdayReq()
        req.ParseFromString(data)
        rsp = ChangeIsHideBirthdayRsp()
        rsp.status = StatusCode.StatusCode_OK

        current_status = db.get_players_info(
            session.player_id, "is_hide_birthday"
        )  # 获取当前状态
        new_status = 0 if current_status else 1

        db.set_players_info(session.player_id, "is_hide_birthday", new_status)

        session.send(
            MsgId.ChangeIsHideBirthdayRsp, rsp, packet_id
        )  # 更改是否隐藏生日 2313 2314
