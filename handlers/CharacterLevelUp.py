from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CharacterLevelUpReq_pb2
import proto.OverField_pb2 as CharacterLevelUpRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 角色升级 1039 1040
"""


@packet_handler(CmdId.CharacterLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelUpReq_pb2.CharacterLevelUpReq()
        req.ParseFromString(data)

        rsp = CharacterLevelUpRsp_pb2.CharacterLevelUpRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.char_id = req.char_id  # 从请求获取
        rsp.level = TEST_DATA["level"]
        rsp.exp = TEST_DATA["exp"]

        session.send(CmdId.CharacterLevelUpRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "level": 20, "exp": 0}
