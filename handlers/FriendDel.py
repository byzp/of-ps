from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    FriendDelReq,
    FriendDelRsp,
    FriendHandleType,
)

from server import social
from server.scene_data import get_session


@packet_handler(MsgId.FriendDelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendDelReq()
        req.ParseFromString(data)

        status, removed = social.remove_friend(session.player_id, req.player_id)
        rsp = FriendDelRsp(status=status)
        session.send(MsgId.FriendDelRsp, rsp, packet_id)
        if removed:
            social.send_friend_notice(
                session.player_id,
                req.player_id,
                FriendHandleType.FriendHandleType_DEL,
                get_session(),
                self_session=session,
            )
