from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as UpdateTeamReq_pb2
import proto.OverField_pb2 as UpdateTeamRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.UpdateTeamReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdateTeamReq_pb2.UpdateTeamReq()
        req.ParseFromString(data)

        rsp = UpdateTeamRsp_pb2.UpdateTeamRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        db.set_players_info(
            session.player_id, "team", (req.char_1, req.char_2, req.char_3)
        )
        session.send(CmdId.UpdateTeamRsp, rsp, False, packet_id)

        # TODO 广播场景数据
