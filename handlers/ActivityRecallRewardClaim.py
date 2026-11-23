from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityRecallRewardClaimReq,
    ActivityRecallRewardClaimRsp,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils import achieve_track

"""
# 回归活动领取奖励 4511 4512
"""


@packet_handler(MsgId.ActivityRecallRewardClaimReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityRecallRewardClaimReq()
        req.ParseFromString(data)

        rsp = ActivityRecallRewardClaimRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.activity_id = req.activity_id
        rsp.condition_id = req.condition_id

        if not db.try_claim(
            session.player_id,
            "activity_recall",
            f"{req.activity_id}:{req.condition_id}",
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(
                MsgId.ActivityRecallRewardClaimRsp, rsp, packet_id
            )  # 4511,4512
            return

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        # 回归活动奖励配置未知(condition_id 无表), 暂发500金币
        db.grant_rewards(session.player_id, [(101, 500)], rsp.rewards, pack)

        # 成就: 成功召回玩家
        achieve_track.report(session, "recall_player")
        session.send(MsgId.ActivityRecallRewardClaimRsp, rsp, packet_id)  # 4511,4512
        session.send(MsgId.PackNotice, pack, 0)
