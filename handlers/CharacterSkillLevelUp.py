from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
from proto.net_pb2 import (
    CharacterSkillLevelUpReq,
    CharacterSkillLevelUpRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(MsgId.CharacterSkillLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CharacterSkillLevelUpReq()
        rsp = CharacterSkillLevelUpRsp()
        req.ParseFromString(data)

        rsp.status = StatusCode.StatusCode_OK

        # TODO 技能升级

        session.send(
            MsgId.CharacterSkillLevelUpRsp, rsp, packet_id
        )  # 角色技能升级 1035 1036
