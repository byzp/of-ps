from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeHeadReq_pb2
import proto.OverField_pb2 as ChangeHeadRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 更换头像 1528 1529
"""


@packet_handler(CmdId.ChangeHeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHeadReq_pb2.ChangeHeadReq()
        req.ParseFromString(data)

        rsp = ChangeHeadRsp_pb2.ChangeHeadRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set status from test data
        rsp.status = TEST_DATA["status"]
        
        # Set head from request
        rsp.head = req.head

        session.send(CmdId.ChangeHeadRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}