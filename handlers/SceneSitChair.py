from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as SceneSitChairReq_pb2
import proto.OverField_pb2 as SceneSitChairRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.SceneSitChairReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SceneSitChairReq_pb2.SceneSitChairReq()
        req.ParseFromString(data)

        rsp = SceneSitChairRsp_pb2.SceneSitChairRsp()

        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.player_id = session.player_id
        rsp.chair_id = req.chair_id
        rsp.seat_id = req.seat_id
        rsp.is_sit = req.is_sit

        session.send(MsgId.SceneSitChairRsp, rsp, packet_id)

