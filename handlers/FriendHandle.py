from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as FriendHandleReq_pb2
import proto.OverField_pb2 as FriendHandleRsp_pb2
import proto.OverField_pb2 as FriendHandleNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as FriendHandleType_pb2

import utils.db as db
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendHandleReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendHandleReq_pb2.FriendHandleReq()
        req.ParseFromString(data)

        rsp = FriendHandleRsp_pb2.FriendHandleRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        stat = db.get_friend_info(session.player_id, req.player_id, "friend_status")

        if stat:
            match stat:
                case 0:  # 存在记录但非好友,正常不可能触发
                    pass
                case 1:  # 已发过申请
                    rsp1 = FriendHandleNotice_pb2.FriendHandleNotice()
                    rsp1.status = StatusCode_pb2.StatusCode_OK
                    if req.is_agree:
                        # 双方添加好友
                        db.set_friend_info(
                            req.player_id, session.player_id, "friend_status", 2
                        )
                        db.set_friend_info(
                            session.player_id, req.player_id, "friend_status", 2
                        )

                        rsp1.type = FriendHandleType_pb2.FriendHandleType_ADD
                        rsp1.target_player_id == req.player_id
                        session.send(MsgId.FriendHandleNotice, rsp1, 0)
                        for s in get_session():
                            if s.player_id == req.player_id:
                                rsp1.target_player_id == session.player_id
                                s.send(MsgId.FriendHandleNotice, rsp1, 0)
                                break
                    else:
                        db.del_friend_info(session.player_id, req.player_id)
                        # 对方不需要知道被拒绝
                        rsp1.type = FriendHandleType_pb2.FriendHandleType_DEL
                        rsp1.target_player_id == req.player_id
                        session.send(MsgId.FriendHandleNotice, rsp1, 0)
                case 2:  # 好友,正常也不可能
                    rsp.status = StatusCode_pb2.StatusCode_FRIEND_EXIST
                    session.send(MsgId.FriendHandleRsp, rsp, packet_id)
                    return
                case 3:  # 黑名单
                    if req.is_agree:
                        rsp.status = StatusCode_pb2.StatusCode_FRIEND_BLACK
                        session.send(MsgId.FriendHandleRsp, rsp, packet_id)
                        return
                    else:
                        rsp1 = FriendHandleNotice_pb2.FriendHandleNotice()
                        rsp1.status = StatusCode_pb2.StatusCode_OK
                        db.del_friend_info(session.player_id, req.player_id)
                        rsp1.type = FriendHandleType_pb2.FriendHandleType_DEL
                        rsp1.target_player_id == req.player_id
                        session.send(MsgId.FriendHandleNotice, rsp1, 0)

        session.send(MsgId.FriendHandleRsp, rsp, packet_id)
