from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeSignReq_pb2
import proto.OverField_pb2 as ChangeSignRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 修改签名 1526 1527
"""


@packet_handler(CmdId.ChangeSignReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeSignReq_pb2.ChangeSignReq()
        req.ParseFromString(data)

        rsp = ChangeSignRsp_pb2.ChangeSignRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set status from test data
        rsp.status = TEST_DATA["status"]
        
        # Set sign from request
        rsp.sign = req.sign

        session.send(CmdId.ChangeSignRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}