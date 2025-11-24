from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as NpcTalkReq_pb2
import proto.OverField_pb2 as NpcTalkRsp_pb2

logger = logging.getLogger(__name__)


"""
# NPC对话 1803 1804
"""


@packet_handler(CmdId.NpcTalkReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = NpcTalkReq_pb2.NpcTalkReq()
        req.ParseFromString(data)

        rsp = NpcTalkRsp_pb2.NpcTalkRsp()

        # Set data from test data
        rsp.status = TEST_DATA["status"]

        session.send(CmdId.NpcTalkRsp, rsp, packet_id)

        # Call QuestNotice handler to send quest data notification
        try:
            from handlers.QuestNotice import Handler as QuestNoticeHandler

            quest_notice_handler = QuestNoticeHandler()
            # Create empty data for QuestNotice
            quest_notice_handler.handle(session, b"", packet_id)
        except Exception as e:
            logger.error(f"Failed to send QuestNotice: {e}")


# Hardcoded test data
TEST_DATA = {"status": 1}
