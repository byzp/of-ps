from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as GetCharacterAchievementListReq_pb2
import proto.OverField_pb2 as GetCharacterAchievementListRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetCharacterAchievementListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetCharacterAchievementListReq_pb2.GetCharacterAchievementListReq()
        req.ParseFromString(data)
        chr_id = req.character_id

        rsp = GetCharacterAchievementListRsp_pb2.GetCharacterAchievementListRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        for i in db.get_character_achievement_lst(session.player_id, chr_id):  # TODO
            tmp = rsp.character_achievement_lst.add()
            tmp.achieve_id = 8
            tmp.count = 6
        rsp.character_id = chr_id
        session.send(MsgId.GetCharacterAchievementListRsp, rsp, packet_id)  # 1479,1480
