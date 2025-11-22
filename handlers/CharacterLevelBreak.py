from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import proto.OverField_pb2 as CharacterLevelBreakReq_pb2
import proto.OverField_pb2 as CharacterLevelBreakRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db

logger = logging.getLogger(__name__)


@packet_handler(CmdId.CharacterLevelBreakReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterLevelBreakReq_pb2.CharacterLevelBreakReq()
        rsp = CharacterLevelBreakRsp_pb2.CharacterLevelBreakRsp()
        req.ParseFromString(data)

        character_data = db.get_characters(session.player_id, req.char_id)
        if not character_data:
            rsp.status = StatusCode_pb2.StatusCode_CHARACTER_NOT_FOUND
            rsp.char_id = req.char_id
            session.send(CmdId.CharacterLevelBreakRsp, rsp, False, packet_id)
            return

        character = CharacterLevelBreakReq_pb2.Character()
        character.ParseFromString(character_data[0])
        character.max_level = min(character.max_level + 20, 100)

        db.set_character(session.player_id, req.char_id, character.SerializeToString())

        # 扣除突破手册未实现

        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.char_id = req.char_id
        rsp.level = character.level
        rsp.exp = character.exp
        rsp.max_level = character.max_level

        session.send(
            CmdId.CharacterLevelBreakRsp, rsp, False, packet_id
        )  # 角色突破 1041 1042
