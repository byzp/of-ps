from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetArchiveInfoRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin

logger = logging.getLogger(__name__)


@packet_handler(MsgId.WishListByFriendIdReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetArchiveInfoRsp_pb2.GetArchiveInfoRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # TODO
        session.send(MsgId.WishListByFriendIdRsp, rsp, packet_id)  # 2685,2686
        # session.sbin(2686, bin["2686"])
