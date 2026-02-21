from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    FriendDelReq,
    FriendDelRsp,
    FriendHandleNotice,
    StatusCode,
    FriendHandleType,
)

import utils.db as db
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendDelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendDelReq()
        req.ParseFromString(data)

        rsp = FriendDelRsp()
        rsp.status = StatusCode.StatusCode_OK

        stat = db.get_friend_info(req.player_id, session.player_id, "friend_status")

        if stat:
            match stat:
                case 0:  # 存在记录但非好友,正常不可能触发
                    pass
                case 1:  # 还不是好友,正常不会触发
                    pass
                case 2:  # 好友
                    rsp1 = FriendHandleNotice()
                    rsp1.status = StatusCode.StatusCode_OK
                    # 互删
                    db.del_friend_info(req.player_id, session.player_id)
                    db.del_friend_info(session.player_id, req.player_id)

                    rsp1.type = FriendHandleType.FriendHandleType_DEL
                    rsp1.target_player_id == req.player_id
                    session.send(MsgId.FriendHandleNotice, rsp1, 0)
                    for s in get_session():
                        if s.player_id == req.player_id:
                            rsp1.target_player_id == session.player_id
                            s.send(MsgId.FriendHandleNotice, rsp1, 0)
                            break
                case 3:  # 黑名单,正常不会触发
                    pass

        session.send(MsgId.FriendDelRsp, rsp, packet_id)
