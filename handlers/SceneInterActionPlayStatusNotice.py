from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as SceneInterActionPlayStatusNotice_pb2


logger = logging.getLogger(__name__)

"""
# 场景互动播放状态通知 1333
"""

@packet_handler(CmdId.SceneInterActionPlayStatusNotice)
class Handler(PacketHandler):
    def handle(self, session, data, packet_id: int):
        # Create notice message with hardcoded test data only
        rsp = SceneInterActionPlayStatusNotice_pb2.SceneInterActionPlayStatusNotice()
        rsp.status = TEST_DATA["status"]
        rsp.push_type = TEST_DATA["push_type"]
        rsp.player_id = TEST_DATA["player_id"]

        rsp.action_status.id = TEST_DATA["action_status"]["id"]
        rsp.action_status.value_1 = TEST_DATA["action_status"]["value_1"]
        rsp.action_status.value_2 = TEST_DATA["action_status"]["value_2"]
        rsp.action_status.value_3 = TEST_DATA["action_status"]["value_3"]
        rsp.action_status.value_4 = TEST_DATA["action_status"]["value_4"]
        rsp.action_status.value_5 = TEST_DATA["action_status"]["value_5"]

        session.send(CmdId.SceneInterActionPlayStatusNotice, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "action_status": {
        "id": 80002,
        "value_1": 2030,
        "value_2": 403002,
        "value_3": 0,
        "value_4": 0,
        "value_5": 0,
    },
    "push_type": 1,
    "player_id": 9253197,
}
