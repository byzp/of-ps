from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PlayerEnergyInfoRsp,
    StatusCode,
)

import utils.db as db


@packet_handler(MsgId.PlayerEnergyInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = PlayerEnergyInfoRsp()
        rsp.status = StatusCode.StatusCode_OK

        energy_blob = db.get_item_detail(session.player_id, 11)
        rsp.energy_item.ParseFromString(energy_blob)

        session.send(MsgId.PlayerEnergyInfoRsp, rsp, packet_id)
