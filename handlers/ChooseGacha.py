from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ChooseGachaReq,
    ChooseGachaRsp,
    StatusCode,
)

import utils.db as db


@packet_handler(MsgId.ChooseGachaReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChooseGachaReq()
        req.ParseFromString(data)

        rsp = ChooseGachaRsp()
        rsp.status = StatusCode.StatusCode_OK
        # 选择自选卡池: 持久化到 kv, 重登不丢
        db.set_kv(
            session.player_id, "gacha_choose", str(req.gacha_id), req.choose_gacha_pool
        )
        rsp.choose_gacha_pool = req.choose_gacha_pool
        rsp.gacha_id = req.gacha_id

        session.send(MsgId.ChooseGachaRsp, rsp, packet_id)  # 4543,4544
