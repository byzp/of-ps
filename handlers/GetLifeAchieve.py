from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    Achieve,
    GetLifeAchieveReq,
    GetLifeAchieveRsp,
    LifeBaseInfo,
    StatusCode,
)

import utils.db as db
from utils.life_achieve import conditions_of, proficiency_of, progress_entries
from utils.res_loader import res


def _life_conditions(life_type):
    """该生活类型的成就条件 [(achieve_condition_i_d, 需要熟练度), ...]"""
    return conditions_of(life_type)


@packet_handler(MsgId.GetLifeAchieveReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetLifeAchieveReq()
        req.ParseFromString(data)

        rsp = GetLifeAchieveRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.life_achieve.life_type = req.life_type

        # 生活成就进度(与 GetLifeInfo 同源: 真实 achieve 计数, 零不下发)
        rsp.life_achieve.life_type = req.life_type
        for ach_id, cur in progress_entries(session.player_id, req.life_type):
            tmp = rsp.life_achieve.life_achieve_.add()
            tmp.achieve_id = ach_id
            tmp.count = cur

        for key in db.get_claimed(session.player_id, "life_achieve"):
            if not str(key).lstrip("-").isdigit():
                continue
            rsp.life_achieve.rewarded_life_achieve_id_lst.append(int(key))

        session.send(MsgId.GetLifeAchieveRsp, rsp, packet_id)  # 1391,1392
