from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CharacterLevelBreakReq_pb2
import proto.OverField_pb2 as CharacterLevelBreakRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 角色突破 1041 1042
"""


@packet_handler(CmdId.CharacterLevelBreakReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelBreakReq_pb2.CharacterLevelBreakReq()
        req.ParseFromString(data)

        rsp = CharacterLevelBreakRsp_pb2.CharacterLevelBreakRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.char_id = req.char_id  # 从请求获取
        rsp.level = TEST_DATA["level"]
        rsp.exp = TEST_DATA["exp"]
        rsp.max_level = TEST_DATA["max_level"]

        session.send(CmdId.CharacterLevelBreakRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "level": 20, "exp": 0, "max_level": 40}
