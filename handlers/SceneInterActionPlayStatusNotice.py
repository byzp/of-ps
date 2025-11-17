from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.net_pb2 as SceneInterActionPlayStatusNotice_pb2
import proto.net_pb2 as StatusCode_pb2
import proto.net_pb2 as ScenePlayerActionStatus_pb2
import proto.net_pb2 as InterActionPushType_pb2

logger = logging.getLogger(__name__)


@packet_handler(CmdId.SceneInterActionPlayStatusNotice)
class Handler(PacketHandler):
    def handle(self, session, data, packet_id: int):
        # Create notice message
        notice = SceneInterActionPlayStatusNotice_pb2.SceneInterActionPlayStatusNotice()
        notice.status = StatusCode_pb2.StatusCode_OK
        
        # Check if data is dict (from SceneInterActionPlayStatusReq) or bytes (direct call)
        if isinstance(data, dict):
            # Use data from SceneInterActionPlayStatusReq
            notice.status = TEST_DATA["status"]  # Still using hardcoded status
            notice.push_type = data["push_type"]
            notice.player_id = TEST_DATA["player_id"]  # Still using hardcoded player_id
            
            # Set action_status from request data
            action_status = ScenePlayerActionStatus_pb2.ScenePlayerActionStatus()
            action_status.id = data["action_status"]["id"]
            action_status.value_1 = data["action_status"]["value_1"]
            action_status.value_2 = data["action_status"]["value_2"]
            action_status.value_3 = data["action_status"]["value_3"]
            action_status.value_4 = data["action_status"]["value_4"]
            action_status.value_5 = data["action_status"]["value_5"]
            notice.action_status.CopyFrom(action_status)
        else:
            # Set fields from hardcoded test data (original behavior)
            notice.status = TEST_DATA["status"]
            notice.push_type = TEST_DATA["push_type"]
            notice.player_id = TEST_DATA["player_id"]
            
            # Set action_status
            action_status = ScenePlayerActionStatus_pb2.ScenePlayerActionStatus()
            action_status.id = TEST_DATA["action_status"]["id"]
            action_status.value_1 = TEST_DATA["action_status"]["value_1"]
            action_status.value_2 = TEST_DATA["action_status"]["value_2"]
            action_status.value_3 = TEST_DATA["action_status"]["value_3"]
            action_status.value_4 = TEST_DATA["action_status"]["value_4"]
            action_status.value_5 = TEST_DATA["action_status"]["value_5"]
            notice.action_status.CopyFrom(action_status)

        session.send(CmdId.SceneInterActionPlayStatusNotice, notice, False, packet_id)


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "action_status": {
        "id": 80002,
        "value_1": 2029,
        "value_2": 403002,
        "value_3": 0,
        "value_4": 0,
        "value_5": 0
    },
    "push_type": 1,
    "player_id": 9253086
}