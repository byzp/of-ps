from utils import life_achieve as _la

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    Achieve,
    GetLifeInfoReq,
    GetLifeInfoRsp,
    LifeBaseInfo,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res
from handlers.GetLifeAchieve import _life_conditions

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetLifeInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetLifeInfoReq()
        req.ParseFromString(data)

        rsp = GetLifeInfoRsp()
        rsp.status = StatusCode.StatusCode_OK

        rsp.life_skill.life_type = req.life_type
        # 生活成就进度:
        # 等级表条件成就 + 道具成就族的 **真实 achieve 计数**, 零计数不下发
        rsp.life_achieve.life_type = req.life_type

        for ach_id, cur in _la.progress_entries(session.player_id, req.life_type):
            tmp = rsp.life_achieve.life_achieve_.add()
            tmp.achieve_id = ach_id
            tmp.count = cur

        for key in db.get_claimed(session.player_id, "life_achieve"):
            if not key.isdigit():
                continue
            rsp.life_achieve.rewarded_life_achieve_id_lst.append(int(key))

        _base_blob = db.get_life(session.player_id, req.life_type)
        if isinstance(_base_blob, (bytes, bytearray)):
            rsp.life_base_info.ParseFromString(_base_blob)

        session.send(MsgId.GetLifeInfoRsp, rsp, packet_id)  # 1369,1370
