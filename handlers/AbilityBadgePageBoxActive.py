from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AbilityBadgePageBoxActiveReq,
    AbilityBadgePageBoxActiveRsp,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item, make_QuestNotice


@packet_handler(MsgId.AbilityBadgePageBoxActiveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbilityBadgePageBoxActiveReq()
        req.ParseFromString(data)

        rsp = AbilityBadgePageBoxActiveRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.page = req.page
        rsp.box_id = req.box_id
        ids = db.get_ability_tree(session.player_id, req.page)
        if not req.box_id in ids:
            ids.append(req.box_id)
            db.set_ability_tree(session.player_id, req.page, ids)  # TODO 星符消耗和奖励
            rsp1 = make_QuestNotice(session, [11000321])
            if rsp1:
                session.send(MsgId.QuestNotice, rsp1, 0)

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        if req.page == 1 and req.box_id == 31:
            tmp = rsp.items.add()
            make_item(101000000, 1, session.player_id, tmp)  # 二段跳
            rsp1.items.add().CopyFrom(tmp)
            db.set_item_detail(
                session.player_id,
                tmp.SerializeToString(),
                101000000,
                None,
            )

        session.send(MsgId.PackNotice, rsp1, 0)
        session.send(MsgId.AbilityBadgePageBoxActiveRsp, rsp, packet_id)
