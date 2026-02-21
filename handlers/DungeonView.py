from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import DungeonViewReq, DungeonViewRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.DungeonViewReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonViewReq()
        req.ParseFromString(data)

        rsp = DungeonViewRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.dungeon_data.dungeon_id = req.dungeon_id

        session.send(MsgId.DungeonViewRsp, rsp, packet_id)
