from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as RiddleStateUpdateReq_pb2
import proto.OverField_pb2 as RiddleStateUpdateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 谜题状态更新 1323 1324
"""


@packet_handler(CmdId.RiddleStateUpdateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = RiddleStateUpdateReq_pb2.RiddleStateUpdateReq()
        req.ParseFromString(data)

        rsp = RiddleStateUpdateRsp_pb2.RiddleStateUpdateRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # 从请求中获取riddle_id和state
        riddle_data = rsp.riddle_data
        riddle_data.riddle_id = req.riddle_id
        riddle_data.state = req.battle_state
        riddle_data.is_win = req.is_win

        session.send(CmdId.RiddleStateUpdateRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
