from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import DungeonFinishReq, DungeonFinishRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonFinishReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonFinishReq()
        req.ParseFromString(data)

        rsp = DungeonFinishRsp()
        rsp.status = StatusCode.StatusCode_OK
        # TODO ?

        session.send(MsgId.DungeonFinishRsp, rsp, packet_id)
