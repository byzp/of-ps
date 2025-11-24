from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as OutfitPresetSwitchReq_pb2
import proto.OverField_pb2 as OutfitPresetSwitchRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 切换服装预设 1659 1660
# 只实现了响应 还没处理数据库
"""


@packet_handler(CmdId.OutfitPresetSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitPresetSwitchReq_pb2.OutfitPresetSwitchReq()
        req.ParseFromString(data)

        rsp = OutfitPresetSwitchRsp_pb2.OutfitPresetSwitchRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.char_id = req.char_id
        rsp.use_preset_index = req.use_preset_index

        session.send(CmdId.OutfitPresetSwitchRsp, rsp, packet_id)
