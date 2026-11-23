from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import GetAchieveGroupListRsp, StatusCode

import utils.db as db


@packet_handler(MsgId.GetAchieveGroupListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GetAchieveGroupListRsp()
        rsp.status = StatusCode.StatusCode_OK
        # 已领取奖励的分组(GetAchieveGroupAward 持久化于 claimed_rewards)
        for group_id in db.get_claimed(session.player_id, "achieve_group"):
            if isinstance(group_id, str) and group_id.strip().lstrip("+-").isdigit():
                rsp.rewarded_group_id_lst.append(int(group_id))
            elif isinstance(group_id, int):
                rsp.rewarded_group_id_lst.append(int(group_id))
        session.send(MsgId.GetAchieveGroupListRsp, rsp, packet_id)  # 1757,1758
