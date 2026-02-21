from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    UpdatePlayerAppearanceReq,
    UpdatePlayerAppearanceRsp,
    StatusCode,
)
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.UpdatePlayerAppearanceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdatePlayerAppearanceReq()
        req.ParseFromString(data)

        rsp = UpdatePlayerAppearanceRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.appearance.avatar_frame = req.appearance.avatar_frame
        rsp.appearance.pendant = req.appearance.pendant

        db.set_players_info(
            session.player_id, "avatar_frame", req.appearance.avatar_frame
        )
        db.set_players_info(session.player_id, "pendant", req.appearance.pendant)

        session.send(
            MsgId.UpdatePlayerAppearanceRsp, rsp, packet_id
        )  # 更换头像框 挂件 2631 2632
