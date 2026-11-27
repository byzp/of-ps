from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import ExploreInitReq, ExploreInitRsp, StatusCode
import utils.garden_state as garden_state
from handlers.Explore import _rows, load_activity_state, load_area_state

"""
# 探索初始化 1819 1820
探索进度统一走 utils/garden_state 内存态,
与 Explore/ExploreCollectReward 等 handler 的读写口径保持一致;
探索点清单/采集物取 Explore.json explore_area
"""


@packet_handler(MsgId.ExploreInitReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreInitReq()
        req.ParseFromString(data)

        rsp = ExploreInitRsp()
        rsp.status = StatusCode.StatusCode_OK

        for explore_id in garden_state.explore_area_ids():
            try:
                e = load_area_state(session.player_id, explore_id)
            except (ValueError, TypeError):
                continue
            garden_state.fill_explore_info(rsp.explore.add(), explore_id, e)

        # activity_explore: 回填全部已配置活动, 损坏记录不伪造完成状态。
        for activity in _rows("Explore", "explore_activity"):
            try:
                st = load_activity_state(session.player_id, str(activity["i_d"]))
            except (KeyError, ValueError, TypeError):
                continue
            info = rsp.activity_explore.add()
            info.explore_id = activity["i_d"]
            info.times = st["times"]
            info.is_quick_finish = st["is_quick_finish"]
            if st["start_time"]:
                info.start_time = st["start_time"]
                info.collect_reward = st["collectable"]

        session.send(MsgId.ExploreInitRsp, rsp, packet_id)  # 1819,1820
