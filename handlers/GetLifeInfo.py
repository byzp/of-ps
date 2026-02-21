from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GetLifeInfoReq, GetLifeInfoRsp, StatusCode

import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetLifeInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetLifeInfoReq()
        req.ParseFromString(data)

        rsp = GetLifeInfoRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.life_skill.life_type = req.life_type
        rsp.life_achieve.life_type = req.life_type  # TODO
        rsp.life_base_info.ParseFromString(
            db.get_life(session.player_id, req.life_type)
        )

        session.send(MsgId.GetLifeInfoRsp, rsp, packet_id)  # 1369,1370
