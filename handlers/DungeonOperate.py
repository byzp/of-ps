from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import DungeonOperateReq, DungeonOperateRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonOperateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonOperateReq()
        req.ParseFromString(data)

        rsp = DungeonOperateRsp()
        rsp.status = StatusCode.StatusCode_OK
        # TODO 耗时和星级

        session.send(MsgId.DungeonOperateRsp, rsp, packet_id)
