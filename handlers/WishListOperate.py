from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import time

from proto.net_pb2 import (
    WishListOperateReq,
    WishListOperateRsp,
    WishListOperateType,
    StatusCode,
)

import server.photo_share as ps


@packet_handler(MsgId.WishListOperateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WishListOperateReq()
        req.ParseFromString(data)

        rsp = WishListOperateRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.operate_type = req.operate_type
        rsp.shop_id = req.shop_id
        rsp.grid_id = req.grid_id

        pool_id = ps.find_wish_pool_id(req.shop_id, req.grid_id)
        rsp.pool_id = pool_id

        key = (req.shop_id, req.grid_id)
        # 心愿单经 photo_share 快照持久化
        with ps.lock_wish:
            wish = ps.wish_lists.setdefault(session.player_id, {})
            if req.operate_type == WishListOperateType.WishListOperateType_Add:
                if key in wish:
                    rsp.status = StatusCode.StatusCode_WISH_LIST_EXIST
                elif len(wish) >= ps.WISH_LIST_MAX:
                    rsp.status = StatusCode.StatusCode_WISH_LIST_LIMIT
                else:
                    wish[key] = {
                        "shop_id": req.shop_id,
                        "grid_id": req.grid_id,
                        "pool_id": pool_id,
                        "create_time": int(time.time()),
                    }
            elif req.operate_type == WishListOperateType.WishListOperateType_Del:
                if key in wish:
                    del wish[key]
                else:
                    rsp.status = StatusCode.StatusCode_WISH_LIST_NOT_EXIST

        session.send(MsgId.WishListOperateRsp, rsp, packet_id)  # 2681,2682
