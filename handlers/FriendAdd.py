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
        )  # 设置成申请中状态

        # TODO: 添加到players表plapply_list字段 JSON格式 用于目标玩家申请列表响应

        rsp = FriendAddRsp_pb2.FriendAddRsp()
        rsp.status = FriendAddRsp_pb2.StatusCode_OK

        session.send(CmdId.FriendAddRsp, rsp, packet_id)

        # TODO: 判断目标玩家在线状态 发送好友处理通知
