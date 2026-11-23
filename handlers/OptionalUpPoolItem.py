from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import pickle

from proto.net_pb2 import (
    OptionalUpPoolItemReq,
    OptionalUpPoolItemRsp,
    StatusCode,
)

import utils.db as db


@packet_handler(MsgId.OptionalUpPoolItemReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OptionalUpPoolItemReq()
        req.ParseFromString(data)

        rsp = OptionalUpPoolItemRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 自选UP物品: 持久化到 kv, 重登不丢
        db.set_kv(
            session.player_id,
            "gacha_optional_up",
            str(req.gacha_id),
            pickle.dumps({"item_id": req.item_id, "pool_id": req.poo_id}),
        )
        rsp.info.gacha_id = req.gacha_id
        rsp.info.gacha_times = db.get_total_gacha_num(session.player_id, req.gacha_id)
        rsp.info.guarantee = 70 - db.get_gacha_guarantee(
            session.player_id, req.gacha_id
        )
        rsp.info.optional_up_item = req.item_id
        rsp.info.choose_pool_id = req.poo_id

        session.send(MsgId.OptionalUpPoolItemRsp, rsp, packet_id)  # 2207,2208
