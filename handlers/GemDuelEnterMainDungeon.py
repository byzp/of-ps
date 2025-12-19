from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GemDuelEnterMainDungeonReq_pb2
import proto.OverField_pb2 as GemDuelEnterMainDungeonRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GemDuelEnterMainDungeonReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GemDuelEnterMainDungeonReq_pb2.GemDuelEnterMainDungeonReq()
        req.ParseFromString(data)

        rsp = GemDuelEnterMainDungeonRsp_pb2.GemDuelEnterMainDungeonRsp()  # TODO
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.game_data.gaem_type = StatusCode_pb2.GEM_DUEL_GAME_PVE
        tmp = rsp.game_data.players.add()
        tmp.player_id = session.player_id
        tmp.player_type = 1
        tmp1 = tmp.characters.add()
        tmp1.id = 1
        tmp.attack = 1
        tmp.index = 1

        session.send(MsgId.GemDuelEnterMainDungeonRsp, rsp, packet_id)
