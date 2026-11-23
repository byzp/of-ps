from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    GetAchieveOneGroupRsp,
    GetAchieveOneGroupReq,
    Achieve,
    StatusCode,
)
import utils.db as db
from utils import achieve_track
from utils.res_loader import res


@packet_handler(MsgId.GetAchieveOneGroupReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetAchieveOneGroupReq()
        req.ParseFromString(data)

        rsp = GetAchieveOneGroupRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.current_group_achieve_info.group_id = req.group_id
        # 组奖励领取状态(与 GetAchieveGroupAward 同存储)
        rsp.is_reward = req.group_id in {
            int(k) for k in db.get_claimed(session.player_id, "achieve_group")
        }
        group = next(
            (
                row
                for row in res["AchieveQuest"]["achieve_quest_group"]["datas"]
                if row.get("i_d") == req.group_id
            ),
            None,
        )
        if group:
            achieve_ids = [
                info["achieve_condition_i_d"]
                for info in group.get("achieve_quest_group_info") or ()
                if isinstance(info, dict) and info.get("achieve_condition_i_d")
            ]
            achieve_track.sync_scoped_progress(session, achieve_ids)
            for achieve_id in achieve_ids:
                achieve = db.get_achieve(session.player_id, achieve_id)
                if not achieve:
                    continue
                tmp = Achieve()
                tmp.ParseFromString(achieve)
                if tmp.count <= 0:
                    continue
                lst = rsp.current_group_achieve_info.achieve_lst.add()
                lst.ParseFromString(achieve)

        session.send(MsgId.GetAchieveOneGroupRsp, rsp, packet_id)  # 1761,1762, 成就
