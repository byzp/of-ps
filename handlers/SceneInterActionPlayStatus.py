from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.net_pb2 as SceneInterActionPlayStatusReq_pb2
import proto.net_pb2 as SceneInterActionPlayStatusRsp_pb2
import proto.net_pb2 as StatusCode_pb2

# Import SceneInterActionPlayStatusNotice handler
from handlers.SceneInterActionPlayStatusNotice import (
    Handler as SceneInterActionPlayStatusNoticeHandler,
)

logger = logging.getLogger(__name__)


@packet_handler(CmdId.SceneInterActionPlayStatusReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SceneInterActionPlayStatusReq_pb2.SceneInterActionPlayStatusReq()
        req.ParseFromString(data)

        rsp = SceneInterActionPlayStatusRsp_pb2.SceneInterActionPlayStatusRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        # Set fields from hardcoded test data
        rsp.status = TEST_DATA["status"]

        # Call SceneInterActionPlayStatusNotice handler to send notice
        try:
            notice_handler = SceneInterActionPlayStatusNoticeHandler()
            # Pass request data to SceneInterActionPlayStatusNotice
            notice_data = {
                "action_status": {
                    "id": req.action_status.id,
                    "value_1": req.action_status.value_1,
                    "value_2": req.action_status.value_2,
                    "value_3": req.action_status.value_3,
                    "value_4": req.action_status.value_4,
                    "value_5": req.action_status.value_5,
                },
                "push_type": req.push_type,
            }
            notice_handler.handle(session, notice_data, packet_id)
        except Exception as e:
            logger.error(f"Failed to send SceneInterActionPlayStatusNotice: {e}")

        session.send(CmdId.SceneInterActionPlayStatusRsp, rsp, False, packet_id)


# Hardcoded test data
TEST_DATA = {"status": 1}
