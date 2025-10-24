from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as FriendReq_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.FriendReq)
class GetArchiveInfoHandler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = FriendReq_pb2.FriendRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.send(CmdId.FriendRsp, rsp, False, packet_id)  # 1739,1740
        # session.sbin(CmdId.FriendRsp, "tmp\\bin\\packet_66_1740_servertoclient_body.bin")
