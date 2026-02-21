from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import GetAchieveOneGroupRsp, GetAchieveOneGroupReq, StatusCode
import utils.db as db
from utils.res_loader import res

logger = logging.getLogger(__name__)


@packet_handler(MsgId.GetAchieveOneGroupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetAchieveOneGroupReq()
        req.ParseFromString(data)

        rsp = GetAchieveOneGroupRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.current_group_achieve_info.group_id = req.group_id
        for group in res["AchieveQuest"]["achieve_quest_group"]["datas"]:
            if group["i_d"] == req.group_id:
                for group_info in group["achieve_quest_group_info"]:
                    lst = rsp.current_group_achieve_info.achieve_lst.add()
                    achieve = db.get_achieve(
                        session.player_id, group_info["achieve_condition_i_d"]
                    )
                    if not achieve:
                        continue
                    lst.ParseFromString(achieve)

        session.send(MsgId.GetAchieveOneGroupRsp, rsp, packet_id)  # 1761,1762, 成就
