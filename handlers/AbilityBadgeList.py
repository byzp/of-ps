from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AbilityBadgeListReq,
    AbilityBadgeListRsp,
    StatusCode,
)

import utils.db as db


@packet_handler(MsgId.AbilityBadgeListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbilityBadgeListReq()
        req.ParseFromString(data)

        rsp = AbilityBadgeListRsp()
        rsp.status = StatusCode.StatusCode_OK
        if req.scene_id:
            page = rsp.ability_badge_pages.add()
            page.page = req.scene_id
            page.active_box_ids.extend(
                db.get_ability_tree(session.player_id, req.scene_id)
            )
        else:
            for k, v in db.get_ability_tree(session.player_id).items():
                page = rsp.ability_badge_pages.add()
                page.page = k
                page.active_box_ids.extend(v)

        session.send(MsgId.AbilityBadgeListRsp, rsp, packet_id)
