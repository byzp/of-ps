from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeIsHideBirthdayReq_pb2
import proto.OverField_pb2 as ChangeIsHideBirthdayRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 更改是否隐藏生日 2313 2314
"""


@packet_handler(CmdId.ChangeIsHideBirthdayReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeIsHideBirthdayReq_pb2.ChangeIsHideBirthdayReq()
        req.ParseFromString(data)

        rsp = ChangeIsHideBirthdayRsp_pb2.ChangeIsHideBirthdayRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set status from test data
        rsp.status = TEST_DATA["status"]

        session.send(CmdId.ChangeIsHideBirthdayRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}