from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as SystemNotice_pb2

logger = logging.getLogger(__name__)


"""
# 系统通知 2016
"""


@packet_handler(CmdId.SystemNotice)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = SystemNotice_pb2.SystemNotice()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        # Set notice data
        notice = rsp.notice
        notice.notice_id = TEST_DATA["notice"]["notice_id"]
        notice.scene_id = TEST_DATA["notice"]["scene_id"]
        notice.channel_id = TEST_DATA["notice"]["channel_id"]

        # Add params
        for param in TEST_DATA["notice"]["param"]:
            notice.param.append(param)

        session.send(CmdId.SystemNotice, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "notice": {
        "notice_id": 1,
        "param": ["测试玩家", "301002"],  # 玩家名称  # 角色ID
        "scene_id": 9999,  # 抽卡通知场景ID
        "channel_id": 1,  # 抽卡通知频道
    },
}
