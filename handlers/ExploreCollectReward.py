from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import ExploreCollectRewardReq, ExploreCollectRewardRsp, PackNotice, StatusCode
import utils.garden_state as garden_state
import utils.db as db
from utils import achieve_track, item_mgr
from handlers.Explore import area_rewards


@packet_handler(MsgId.ExploreCollectRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreCollectRewardReq()
        req.ParseFromString(data)
        rsp = ExploreCollectRewardRsp(
            is_activity=req.is_activity, explore_id=req.explore_id
        )
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        if req.is_activity:
            # 活动探索的产出已在 ExploreReward 一次性发放, 没有独立收集奖池。
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ExploreCollectRewardRsp, rsp, packet_id)
            return
        try:
            item_mgr.validate_count(
                Config.EXPLORE_COLLECT_REWARD_COUNT, label="explore collect count"
            )
            rewards = [
                (item_id, Config.EXPLORE_COLLECT_REWARD_COUNT)
                for item_id, _ in area_rewards(req.explore_id)
            ]
            with item_mgr.player_lock(session.player_id), db.transaction():
                state = garden_state.get_explore(session.player_id, req.explore_id)
                if state.get("collect_reward"):
                    rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                else:
                    item_mgr.grant_items(
                        session.player_id,
                        rewards,
                        rsp_items=rsp.reward_item,
                        pack_notice=pack,
                        session=session,
                    )
                    state["collect_reward"] = True
                    garden_state.set_explore(session.player_id, req.explore_id, state)
                    rsp.status = StatusCode.StatusCode_OK
                garden_state.fill_explore_info(rsp.explore, req.explore_id, state)
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.reward_item[:]
            del pack.items[:]
        session.send(MsgId.ExploreCollectRewardRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        achieve_track.report(session, "explore_collect_reward")
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
