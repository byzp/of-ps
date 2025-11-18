from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeHideTypeReq_pb2
import proto.OverField_pb2 as ChangeHideTypeRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 更改渠道隐藏类型 2317 2318
"""


@packet_handler(CmdId.ChangeHideTypeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeHideTypeReq_pb2.ChangeHideTypeReq()
        req.ParseFromString(data)

        rsp = ChangeHideTypeRsp_pb2.ChangeHideTypeRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set status from test data
        rsp.status = TEST_DATA["status"]
        
        # Set hide_value (0 or 1)
        rsp.hide_value = TEST_DATA["hide_value"]

        session.send(CmdId.ChangeHideTypeRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "hide_value": 1}  # Can be 0 or 1
