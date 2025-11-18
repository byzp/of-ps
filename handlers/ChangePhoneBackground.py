from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangePhoneBackgroundReq_pb2
import proto.OverField_pb2 as ChangePhoneBackgroundRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 更换手机背景 1517 1518
"""


@packet_handler(CmdId.ChangePhoneBackgroundReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangePhoneBackgroundReq_pb2.ChangePhoneBackgroundReq()
        req.ParseFromString(data)

        rsp = ChangePhoneBackgroundRsp_pb2.ChangePhoneBackgroundRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set status from test data
        rsp.status = TEST_DATA["status"]
        
        # Set phone_background from request
        rsp.phone_background = req.phone_background

        session.send(CmdId.ChangePhoneBackgroundRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
