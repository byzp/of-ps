from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import ReportReq, ReportRsp, StatusCode

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ReportReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ReportReq()
        req.ParseFromString(data)

        logger.info(
            "玩家举报 reporter=%s report_status=%s chat_channel=%s "
            "reported_player_id=%s reported_role_name=%s reported_role_level=%s "
            "reason=%s chat_content=%s code=%s",
            session.player_id,
            req.report_status,
            req.chat_channel,
            req.reported_player_id,
            req.reported_role_name,
            req.reported_role_level,
            req.reason,
            req.chat_content,
            req.code,
        )

        rsp = ReportRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.ReportRsp, rsp, packet_id)  # 2170,2171
