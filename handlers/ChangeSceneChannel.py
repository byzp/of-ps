from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as ChangeSceneChannelReq_pb2
import proto.OverField_pb2 as ChangeSceneChannelRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

# Import SceneDataNotice handler
from handlers.SceneDataNotice import Handler as SceneDataNoticeHandler

logger = logging.getLogger(__name__)


@packet_handler(CmdId.ChangeSceneChannelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeSceneChannelReq_pb2.ChangeSceneChannelReq()
        req.ParseFromString(data)

        rsp = ChangeSceneChannelRsp_pb2.ChangeSceneChannelRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set scene_id from request
        rsp.scene_id = req.scene_id
        
        # Hardcoded test data for other fields
        rsp.channel_id = TEST_DATA["channel_id"]
        rsp.channel_label = TEST_DATA["channel_label"]
        rsp.password_allow_time = TEST_DATA["password_allow_time"]
        rsp.target_player_id = TEST_DATA["target_player_id"]

        session.send(CmdId.ChangeSceneChannelRsp, rsp, False, packet_id)
        
        # Call SceneDataNotice handler to send scene data notification
        try:
            scene_data_handler = SceneDataNoticeHandler()
            # Create empty data for SceneDataNotice
            scene_data_handler.handle(session, b"", packet_id)
        except Exception as e:
            logger.error(f"Failed to send SceneDataNotice: {e}")


# Hardcoded test data
TEST_DATA = {
    "status": 1,
    "scene_id": 1,
    "channel_id": 1524,
    "channel_label": 0,
    "password_allow_time": 0,
    "target_player_id": 0
}