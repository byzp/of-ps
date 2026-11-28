from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    FriendHandleReq,
    FriendHandleRsp,
    FriendHandleType,
    StatusCode,
)

from server import social
from server.scene_data import get_session
from utils import achieve_track


logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendHandleReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendHandleReq()
        req.ParseFromString(data)

        status, accepted = social.handle_friend(
            session.player_id, req.player_id, req.is_agree
        )
        rsp = FriendHandleRsp(status=status)
        session.send(MsgId.FriendHandleRsp, rsp, packet_id)
        if not accepted:
            if status == StatusCode.StatusCode_OK:
                # 有效拒绝：通知本地列表移除待申请项。
                social.send_friend_notice(
                    session.player_id,
                    req.player_id,
                    FriendHandleType.FriendHandleType_DEL,
                    (),
                    self_session=session,
                )
            return

        # 关系已提交；成就失败不得回滚或阻止双方收到关系通知。
        try:
            achieve_track.report(session, "new_friend")
        except Exception:
            logger.exception("Failed to report new_friend achievement")
        social.send_friend_notice(
            session.player_id,
            req.player_id,
            FriendHandleType.FriendHandleType_ADD,
            get_session(),
            self_session=session,
        )
