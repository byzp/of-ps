from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as DungeonOperateReq_pb2
import proto.OverField_pb2 as DungeonOperateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonOperateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonOperateReq_pb2.DungeonOperateReq()
        req.ParseFromString(data)

        rsp = DungeonOperateRsp_pb2.DungeonOperateRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # TODO 耗时和星级

        session.send(MsgId.DungeonOperateRsp, rsp, packet_id)
