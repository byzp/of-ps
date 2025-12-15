from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as FriendAddReq_pb2
import proto.OverField_pb2 as FriendAddRsp_pb2
import proto.OverField_pb2 as FriendHandleNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as FriendHandleType_pb2

import utils.db as db
from server.scene_data import get_session

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendAddReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendAddReq_pb2.FriendAddReq()
        req.ParseFromString(data)

        rsp = FriendAddRsp_pb2.FriendAddRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        stat = db.get_friend_info(req.player_id, session.player_id, "friend_status")

        if stat:
            match stat:
                case 0:  # 存在记录但非好友,正常不可能触发
                    pass
                case 1:  # 已发过申请
                    rsp.status = StatusCode_pb2.StatusCode_FRIEND_APPLY_EXIST
                    session.send(MsgId.FriendAddRsp, rsp, packet_id)
                    return
                case 2:  # 好友,正常也不可能
                    rsp.status = StatusCode_pb2.StatusCode_FRIEND_EXIST
                    session.send(MsgId.FriendAddRsp, rsp, packet_id)
                    return
                case 3:  # 黑名单
                    rsp.status = StatusCode_pb2.StatusCode_FRIEND_BLACK
                    session.send(MsgId.FriendAddRsp, rsp, packet_id)
                    return

        db.init_friend(req.player_id, session.player_id)  # 初始化好友关系
        db.set_friend_info(
            req.player_id, session.player_id, "friend_status", 1
        )  # 设置目标玩家为 被申请状态
        session.send(MsgId.FriendAddRsp, rsp, packet_id)

        for s in get_session():
            if s.player_id == req.player_id:
                rsp = FriendHandleNotice_pb2.FriendHandleNotice()
                rsp.status = StatusCode_pb2.StatusCode_OK
                rsp.type = FriendHandleType_pb2.FriendHandleType_APPLY
                rsp.target_player_id == session.player_id
                s.send(MsgId.FriendHandleNotice, rsp, 0)
                return
