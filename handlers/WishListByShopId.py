from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import WishListByShopIdReq, WishListByShopIdRsp, StatusCode

import utils.db as db
from utils.pb_create import make_PlayerBriefInfo
import server.photo_share as ps


@packet_handler(MsgId.WishListByShopIdReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WishListByShopIdReq()
        req.ParseFromString(data)

        rsp = WishListByShopIdRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 查询把该商品加入心愿单的好友
        key = (req.shop_id, req.grid_id)
        with ps.lock_wish:
            wisher_ids = [pid for pid, wish in ps.wish_lists.items() if key in wish]
            rsp.week_send_count = ps.week_send_count.get(session.player_id, 0)

        for friend_info in db.get_friend_info(
            session.player_id,
            None,
            "friend_id,friend_status,alias,friend_tag,friend_intimacy,friend_background",
        ):
            if friend_info[1] != 2:  # 仅正式好友(1=申请中, 2=好友, 见 FriendHandle)
                continue
            if friend_info[0] not in wisher_ids:
                continue
            info = rsp.info.add()
            info.alias = friend_info[2]
            info.friend_tag = friend_info[3]
            info.friend_intimacy = friend_info[4]
            info.friend_background = friend_info[5]
            make_PlayerBriefInfo(friend_info[0], info.info)

        session.send(MsgId.WishListByShopIdRsp, rsp, packet_id)  # 2683,2684
