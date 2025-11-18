from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CharacterStarUpReq_pb2
import proto.OverField_pb2 as CharacterStarUpRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 角色升星 1037 1038
"""


@packet_handler(CmdId.CharacterStarUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterStarUpReq_pb2.CharacterStarUpReq()
        req.ParseFromString(data)

        rsp = CharacterStarUpRsp_pb2.CharacterStarUpRsp()
        
        # Set data from test data
        rsp.status = TEST_DATA["status"]
        rsp.char_id = req.char_id  # 从请求获取
        rsp.star = TEST_DATA["star"]
        
        # 添加空的items数组
        # items字段已经在proto中定义为repeated ItemDetail，初始为空数组

        session.send(CmdId.CharacterStarUpRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1, "star": 5, "items": [],}