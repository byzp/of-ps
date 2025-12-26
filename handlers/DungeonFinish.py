from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as DungeonFinishReq_pb2
import proto.OverField_pb2 as DungeonFinishRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonFinishReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonFinishReq_pb2.DungeonFinishReq()
        req.ParseFromString(data)

        rsp = DungeonFinishRsp_pb2.DungeonFinishRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # TODO ?

        session.send(MsgId.DungeonFinishRsp, rsp, packet_id)
