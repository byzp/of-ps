from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as DungeonViewReq_pb2
import proto.OverField_pb2 as DungeonViewRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonViewReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonViewReq_pb2.DungeonViewReq()
        req.ParseFromString(data)

        rsp = DungeonViewRsp_pb2.DungeonViewRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.dungeon_data.dungeon_id = req.dungeon_id

        session.send(MsgId.DungeonViewRsp, rsp, packet_id)
