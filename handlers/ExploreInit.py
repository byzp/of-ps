import pickle as _pk

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import ExploreInitReq, ExploreInitRsp, StatusCode
import utils.garden_state as garden_state
import utils.db as db
from utils.res_loader import res

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
            e = garden_state.get_explore(session.player_id, explore_id)
            garden_state.fill_explore_info(rsp.explore.add(), explore_id, e)

        # activity_explore: Explore.explore_activity(单活动 901)状态回填
        _act = next(iter(res["Explore"]["explore_activity"]["datas"]), None)
        if _act:
            _raw = db.get_kv(
                session.player_id,
                "activity_explore",
                str(_act["i_d"]),
                b"",
            )

            st = _pk.loads(_raw) if _raw else {}
            info = rsp.activity_explore.add()
            info.explore_id = _act["i_d"]
            info.times = int(st.get("times", 0))
            info.is_quick_finish = bool(st.get("is_quick_finish"))
            if st.get("start_time"):
                info.start_time = int(st["start_time"])
                info.collect_reward = bool(st.get("collectable"))

        session.send(MsgId.ExploreInitRsp, rsp, packet_id)  # 1819,1820
