from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import FriendReq, FriendRsp, StatusCode

import utils.db as db
from utils.pb_create import make_PlayerBriefInfo

logger = logging.getLogger(__name__)


@packet_handler(MsgId.FriendReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = FriendReq()
        req.ParseFromString(data)

        rsp = FriendRsp()
        rsp.status = StatusCode.StatusCode_OK

        for friend_info in db.get_friend_info(
            session.player_id,
            None,
            "friend_id,friend_status,alias,friend_tag,friend_intimacy,friend_background",
        ):
            if req.type == friend_info[1] or req.type == 0:
                info = rsp.info.add()
                info.alias = friend_info[2]
                info.friend_tag = friend_info[3]
                info.friend_intimacy = friend_info[4]
                info.friend_background = friend_info[5]
                make_PlayerBriefInfo(friend_info[0], info.info)

        session.send(MsgId.FriendRsp, rsp, packet_id)  # 1739,1740
