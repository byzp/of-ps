from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GenericSceneBReq, GenericSceneBRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GenericSceneBReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GenericSceneBReq()
        req.ParseFromString(data)

        rsp = GenericSceneBRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.generic_msg_id = req.generic_msg_id  # TODO

        session.send(MsgId.GenericSceneBRsp, rsp, packet_id)  # 2307,2308
