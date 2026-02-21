from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GetArchiveInfoRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.WishListByFriendIdReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetArchiveInfoRsp()
        rsp.status = StatusCode.StatusCode_OK
        # TODO
        session.send(MsgId.WishListByFriendIdRsp, rsp, packet_id)  # 2685,2686
