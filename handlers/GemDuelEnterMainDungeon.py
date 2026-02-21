from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    GemDuelEnterMainDungeonReq,
    GemDuelEnterMainDungeonRsp,
    StatusCode,
)

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GemDuelEnterMainDungeonReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GemDuelEnterMainDungeonReq()
        req.ParseFromString(data)

        rsp = GemDuelEnterMainDungeonRsp()  # TODO
        rsp.status = StatusCode.StatusCode_OK
        rsp.game_data.gaem_type = StatusCode.GEM_DUEL_GAME_PVE
        tmp = rsp.game_data.players.add()
        tmp.player_id = session.player_id
        tmp.player_type = 1
        tmp1 = tmp.characters.add()
        tmp1.id = 1
        tmp.attack = 1
        tmp.index = 1

        session.send(MsgId.GemDuelEnterMainDungeonRsp, rsp, packet_id)
