from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetLifeInfoReq_pb2
import proto.OverField_pb2 as GetLifeInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetLifeInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetLifeInfoReq_pb2.GetLifeInfoReq()
        req.ParseFromString(data)

        rsp = GetLifeInfoRsp_pb2.GetLifeInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.life_skill.life_type = req.life_type
        rsp.life_achieve.life_type = req.life_type  # TODO
        rsp.life_base_info.ParseFromString(
            db.get_life(session.player_id, req.life_type)
        )

        session.send(MsgId.GetLifeInfoRsp, rsp, packet_id)  # 1369,1370
