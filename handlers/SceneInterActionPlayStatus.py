from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as SceneInterActionPlayStatusReq_pb2
import proto.OverField_pb2 as SceneInterActionPlayStatusRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)

"""
# 场景互动播放状态 1331 1332 
"""

@packet_handler(CmdId.SceneInterActionPlayStatusReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SceneInterActionPlayStatusReq_pb2.SceneInterActionPlayStatusReq()
        req.ParseFromString(data)

        rsp = SceneInterActionPlayStatusRsp_pb2.SceneInterActionPlayStatusRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set fields from hardcoded test data
        rsp.status = TEST_DATA["status"]

        session.send(CmdId.SceneInterActionPlayStatusRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
