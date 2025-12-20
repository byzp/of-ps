from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as CollectMoonReq_pb2
import proto.OverField_pb2 as CollectMoonRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


logger = logging.getLogger(__name__)


@packet_handler(MsgId.CollectMoonReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CollectMoonReq_pb2.CollectMoonReq()
        req.ParseFromString(data)

        rsp = CollectMoonRsp_pb2.CollectMoonRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.moon_id = req.moon_id
        # TODO items

        session.send(MsgId.CollectMoonRsp, rsp, packet_id)
