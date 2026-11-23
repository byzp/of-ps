from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import WishListByFriendIdReq, WishListByFriendIdRsp, StatusCode

import server.photo_share as ps


@packet_handler(MsgId.WishListByFriendIdReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WishListByFriendIdReq()
        req.ParseFromString(data)
        req_player_id = req.player_id

        rsp = WishListByFriendIdRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.player_id = req_player_id
        # 返回该玩家心愿单(ps.wish_lists 已持久化)
        with ps.lock_wish:
            wish = ps.wish_lists.get(req_player_id, {})
            for entry in wish.values():
                info = rsp.wish_list.add()
                info.shop_id = entry["shop_id"]
                info.grid_id = entry["grid_id"]
                info.pool_id = entry["pool_id"]
                info.create_time = entry["create_time"]
            rsp.week_send_count = ps.week_send_count.get(req_player_id, 0)

        session.send(MsgId.WishListByFriendIdRsp, rsp, packet_id)  # 2685,2686
