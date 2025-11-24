from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as UpdatePlayerAppearanceReq_pb2
import proto.OverField_pb2 as UpdatePlayerAppearanceRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.UpdatePlayerAppearanceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdatePlayerAppearanceReq_pb2.UpdatePlayerAppearanceReq()
        req.ParseFromString(data)

        rsp = UpdatePlayerAppearanceRsp_pb2.UpdatePlayerAppearanceRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.appearance.avatar_frame = req.appearance.avatar_frame
        rsp.appearance.pendant = req.appearance.pendant

        db.set_players_info(
            session.player_id, "avatar_frame", req.appearance.avatar_frame
        )
        db.set_players_info(session.player_id, "pendant", req.appearance.pendant)

        session.send(
            CmdId.UpdatePlayerAppearanceRsp, rsp, packet_id
        )  # 更换头像框 挂件 2631 2632
