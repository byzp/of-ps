from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ExploreCollectRewardReq,
    ExploreCollectRewardRsp,
    PackNotice,
    StatusCode,
)
import utils.garden_state as garden_state
import utils.db as db
from utils import achieve_track

"""
# 领取探索点收集奖励 1829 1830
采集物取 Explore.json explore_area.explore_area_item
"""


@packet_handler(MsgId.ExploreCollectRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreCollectRewardReq()
        req.ParseFromString(data)

        rsp = ExploreCollectRewardRsp()
        rsp.is_activity = req.is_activity
        rsp.explore_id = req.explore_id

        e = garden_state.get_explore(session.player_id, req.explore_id)
        if e["collect_reward"]:
            # 已经领取过收集奖励
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
            session.send(MsgId.ExploreCollectRewardRsp, rsp, packet_id)  # 1829,1830
            return

        rsp.status = StatusCode.StatusCode_OK
        e["collect_reward"] = True
        garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
        garden_state.set_explore(session.player_id, req.explore_id, e)

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        for item_id in garden_state.explore_collect_items(req.explore_id):
            gain, total = garden_state.grant_stack_item(
                session.player_id, item_id, Config.EXPLORE_COLLECT_REWARD_COUNT
            )
            rsp.reward_item.add().CopyFrom(gain)
            pack.items.add().CopyFrom(total)

        if not req.is_activity:
            # 类型83统计普通探索点收集奖励，活动探索不共用该成就。
            achieve_track.report(session, "explore_collect_reward")
        session.send(MsgId.ExploreCollectRewardRsp, rsp, packet_id)  # 1829,1830
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)  # 背包变化通知
