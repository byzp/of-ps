from starlette.types import Send
from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as UseItemFriendIntimacyReq_pb2
import proto.OverField_pb2 as UseItemFriendIntimacyRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as ItemDetail_pb2
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.UseItemFriendIntimacyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UseItemFriendIntimacyReq_pb2.UseItemFriendIntimacyReq()
        req.ParseFromString(data)
        print(req)

        rsp = UseItemFriendIntimacyRsp_pb2.UseItemFriendIntimacyRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK

        intimacy_map = {1501: 5, 1502: 10, 1503: 20}
        intimacy_increase = intimacy_map.get(req.item_id, 0)

        item_data = db.get_item_detail(session.player_id, req.item_id)
        item = ItemDetail_pb2.ItemDetail()
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
            CmdId.UseItemFriendIntimacyRsp, rsp, packet_id
        )  # 2651 2652 使用道具增加好友亲密度
