from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging
import proto.OverField_pb2 as CharacterSkillLevelUpReq_pb2
import proto.OverField_pb2 as CharacterSkillLevelUpRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as PackNotice_pb2
import utils.db as db
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(CmdId.CharacterSkillLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterSkillLevelUpReq_pb2.CharacterSkillLevelUpReq()
        rsp = CharacterSkillLevelUpRsp_pb2.CharacterSkillLevelUpRsp()
        req.ParseFromString(data)

        rsp.status = StatusCode_pb2.StatusCode_OK

        # TODO 技能升级

        session.send(CmdId.CharacterSkillLevelUpRsp, rsp, packet_id)  # 角色技能升级 1035 1036
