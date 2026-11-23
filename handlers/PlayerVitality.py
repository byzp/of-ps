from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import time

from proto.net_pb2 import PlayerVitalityReq, PlayerVitalityRsp, StatusCode

import utils.db as db
from utils import refresh


@packet_handler(MsgId.PlayerVitalityReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerVitalityReq()
        req.ParseFromString(data)

        rsp = PlayerVitalityRsp()
        rsp.status = StatusCode.StatusCode_OK
        day = str(refresh.day_index())
        rsp.vitality_buy_num = int(
            db.get_kv(session.player_id, "buy", f"vitality:{day}", 0) or 0
        )
        session.send(MsgId.PlayerVitalityRsp, rsp, packet_id)
