from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as UpdatePlayerAppearanceReq_pb2
import proto.OverField_pb2 as UpdatePlayerAppearanceRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 更新玩家外观 2631 2632
# 头像框 挂件
# 只实现了更换 还没处理数据库
"""


@packet_handler(CmdId.UpdatePlayerAppearanceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdatePlayerAppearanceReq_pb2.UpdatePlayerAppearanceReq()
        req.ParseFromString(data)

        rsp = UpdatePlayerAppearanceRsp_pb2.UpdatePlayerAppearanceRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.appearance.avatar_frame = req.appearance.avatar_frame
        rsp.appearance.pendant = req.appearance.pendant

        session.send(CmdId.UpdatePlayerAppearanceRsp, rsp, False, packet_id)
