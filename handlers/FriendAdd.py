from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    FriendAddReq,
    FriendAddRsp,
    FriendHandleType,
)

from server import social
from server.scene_data import get_session


@packet_handler(MsgId.FriendAddReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendAddReq()
        req.ParseFromString(data)

        status, new_application = social.request_friend(session.player_id, req.player_id)
        rsp = FriendAddRsp(status=status)
        session.send(MsgId.FriendAddRsp, rsp, packet_id)
        if new_application:
            social.send_friend_notice(
                session.player_id,
                req.player_id,
                FriendHandleType.FriendHandleType_APPLY,
                get_session(),
            )
