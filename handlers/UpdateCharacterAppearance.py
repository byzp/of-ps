from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as UpdateCharacterAppearanceReq_pb2
import proto.OverField_pb2 as UpdateCharacterAppearanceRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


"""
# 更新玩家外观 1671 1672
# 头衔 伞 昆虫网 伐木斧 水瓶 挖掘锤 采集手套 钓鱼竿
# 只实现了更换 还没处理数据库
"""


@packet_handler(CmdId.UpdateCharacterAppearanceReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UpdateCharacterAppearanceReq_pb2.UpdateCharacterAppearanceReq()
        req.ParseFromString(data)

        rsp = UpdateCharacterAppearanceRsp_pb2.UpdateCharacterAppearanceRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        rsp.char_id = req.char_id

        rsp.appearance.badge = req.appearance.badge
        rsp.appearance.umbrella_id = req.appearance.umbrella_id
        rsp.appearance.insect_net_instance_id = req.appearance.insect_net_instance_id
        rsp.appearance.logging_axe_instance_id = req.appearance.logging_axe_instance_id
        rsp.appearance.water_bottle_instance_id = (
            req.appearance.water_bottle_instance_id
        )
        rsp.appearance.mining_hammer_instance_id = (
            req.appearance.mining_hammer_instance_id
        )
        rsp.appearance.collection_gloves_instance_id = (
            req.appearance.collection_gloves_instance_id
        )
        rsp.appearance.fishing_rod_instance_id = req.appearance.fishing_rod_instance_id

        session.send(CmdId.UpdateCharacterAppearanceRsp, rsp, False, packet_id)
