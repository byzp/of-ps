from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import OutfitPresetSwitchReq, OutfitPresetSwitchRsp, StatusCode

logger = logging.getLogger(__name__)


"""
# 切换服装预设 1659 1660
# 只实现了响应 还没处理数据库
"""


@packet_handler(MsgId.OutfitPresetSwitchReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OutfitPresetSwitchReq()
        req.ParseFromString(data)

        rsp = OutfitPresetSwitchRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.char_id = req.char_id
        rsp.use_preset_index = req.use_preset_index

        session.send(MsgId.OutfitPresetSwitchRsp, rsp, packet_id)
