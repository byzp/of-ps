from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    FriendBlackReq,
    FriendBlackRsp,
    FriendHandleType,
)

from server import social
from server.scene_data import get_session


@packet_handler(MsgId.FriendBlackReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendBlackReq()
        req.ParseFromString(data)

        status, friendship_removed = social.set_blacklist(
            session.player_id, req.player_id, req.is_remove
        )
        rsp = FriendBlackRsp(status=status)
        session.send(MsgId.FriendBlackRsp, rsp, packet_id)
        if friendship_removed:
            social.send_friend_notice(
                session.player_id,
                req.player_id,
                FriendHandleType.FriendHandleType_DEL,
                get_session(),
                self_session=session,
            )
