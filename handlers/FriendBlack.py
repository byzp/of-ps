from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    FriendBlackReq,
    FriendBlackRsp,
    FriendHandleNotice,
    StatusCode,
    FriendHandleType,
)

import utils.db as db
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendBlackReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendBlackReq()
        req.ParseFromString(data)

        rsp = FriendBlackRsp()
        rsp.status = StatusCode.StatusCode_OK

        stat = db.get_friend_info(req.player_id, session.player_id, "friend_status")

        if stat:
            match stat:
                case 0, 1:  # 还不是好友/已发过申请
                    if req.is_remove:
                        db.del_friend_info(session.player_id, req.player_id)
                    else:

                        db.set_friend_info(
                            session.player_id, req.player_id, "friend_status", 3
                        )
                case 2:  # 好友
                    rsp1 = FriendHandleNotice()
                    rsp1.status = StatusCode.StatusCode_OK
                    # 已方拉黑
                    db.set_friend_info(
                        session.player_id, req.player_id, "friend_status", 3
                    )
                    # 从对方好友删除自己
                    db.del_friend_info(req.player_id, session.player_id)

                    rsp1.type = FriendHandleType.FriendHandleType_DEL
                    rsp1.target_player_id == req.player_id
                    session.send(MsgId.FriendHandleNotice, rsp1, 0)
                    for s in get_session():
                        if s.player_id == req.player_id:
                            rsp1.target_player_id == session.player_id
                            s.send(MsgId.FriendHandleNotice, rsp1, 0)
                            break
                case 3:  # 已在黑名单
                    db.del_friend_info(session.player_id, req.player_id)
        else:
            if req.is_remove:
                db.del_friend_info(session.player_id, req.player_id)
            else:
                db.set_friend_info(session.player_id, req.player_id, "friend_status", 3)

        session.send(MsgId.FriendBlackRsp, rsp, packet_id)
