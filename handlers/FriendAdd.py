from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as FriendAddReq_pb2
import proto.OverField_pb2 as FriendAddRsp_pb2
import proto.OverField_pb2 as FriendHandleNotice_pb2
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.FriendAddReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendAddReq_pb2.FriendAddReq()
        req.ParseFromString(data)
        friend_id = req.player_id

        db.set_friend_info(
            session.player_id, friend_id, friend_status=1
        )  # 设置请求方为 申请状态
        db.set_friend_info(
            friend_id, session.player_id, friend_status=4
        )  # 设置目标玩家为 被申请状态

        rsp = FriendAddRsp_pb2.FriendAddRsp()
        rsp.status = FriendAddRsp_pb2.StatusCode_OK

        session.send(CmdId.FriendAddRsp, rsp, packet_id)

        # TODO: 判断目标玩家在线状态 发送好友处理通知
