from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as CharacterEquipUpdateReq_pb2
import proto.OverField_pb2 as CharacterEquipUpdateRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from utils.bin import bin
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.GetCharacterAchievementListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterEquipUpdateReq_pb2.CharacterEquipUpdateReq()
        req.ParseFromString(data)
        chr_id = req.character_id
        db.up_character_equip(
            session.user_id, chr_id, req.equipment_presets.SerializeToString()
        )

        rsp = CharacterEquipUpdateRsp_pb2.CharacterEquipUpdateRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        # TODO instance_id ?
        tmp = rsp.character.add()

        session.send(CmdId.GetCharacterAchievementListRsp, rsp, False, packet_id)
        # session.sbin(1758, bin["1758"], False, packet_id)
