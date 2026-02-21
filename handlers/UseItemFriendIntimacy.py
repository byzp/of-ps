from starlette.types import Send
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    UseItemFriendIntimacyReq,
    UseItemFriendIntimacyRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
)
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.UseItemFriendIntimacyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UseItemFriendIntimacyReq()
        req.ParseFromString(data)

        rsp = UseItemFriendIntimacyRsp()
        rsp.status = StatusCode.StatusCode_OK

        intimacy_map = {1501: 5, 1502: 10, 1503: 20}
        intimacy_increase = intimacy_map.get(req.item_id, 0)

        item_data = db.get_item_detail(session.player_id, req.item_id)
        item = ItemDetail()
        item.ParseFromString(item_data)
        item.main_item.base_item.num -= 1
        db.set_item_detail(
            session.player_id, item.SerializeToString(), req.item_id, None
        )

        current_intimacy = (
            db.get_friend_info(session.player_id, req.friend_id, "friend_intimacy") or 0
        )
        new_intimacy = current_intimacy + intimacy_increase

        db.set_friend_info(
            session.player_id, req.friend_id, "friend_intimacy", new_intimacy
        )
        db.set_friend_info(
            req.friend_id, session.player_id, "friend_intimacy", new_intimacy
        )

        rsp.intimacy = new_intimacy
        rsp.friend_id = req.friend_id
        print(rsp)

        session.send(
            MsgId.UseItemFriendIntimacyRsp, rsp, packet_id
        )  # 2651 2652 使用道具增加好友亲密度

        # 数量更新通知
        rsp = PackNotice()
        rsp.status = StatusCode.StatusCode_OK
        rsp.items.add().CopyFrom(item)

        session.send(MsgId.PackNotice, rsp, packet_id)
