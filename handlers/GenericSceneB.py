from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GenericSceneBReq_pb2
import proto.OverField_pb2 as GenericSceneBRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GenericSceneBReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GenericSceneBReq_pb2.GenericSceneBReq()
        req.ParseFromString(data)

        rsp = GenericSceneBRsp_pb2.GenericSceneBRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.generic_msg_id = req.generic_msg_id  # TODO

        session.send(MsgId.GenericSceneBRsp, rsp, packet_id)  # 2307,2308
        # session.sbin(1758, bin["1758"],  packet_id)
