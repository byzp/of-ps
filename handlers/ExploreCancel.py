from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ExploreCancelReq, ExploreCancelRsp, StatusCode
import utils.garden_state as garden_state
import utils.db as db
from utils.res_loader import res
import pickle

"""
# 取消探索派遣 1827 1828
"""


@packet_handler(MsgId.ExploreCancelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ExploreCancelReq()
        req.ParseFromString(data)

        rsp = ExploreCancelRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.explore_id = req.explore_id
        rsp.is_activity = req.is_activity

        if req.is_activity:
            _act = next(
                (
                    row
                    for row in res["Explore"]["explore_activity"]["datas"]
                    if isinstance(row, dict) and row.get("i_d") == req.explore_id
                ),
                None,
            )
            if not _act:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.ExploreCancelRsp, rsp, packet_id)
                return
            key = str(_act["i_d"])
            raw = db.get_kv(session.player_id, "activity_explore", key, b"")
            st = pickle.loads(raw) if raw else {}
            info = rsp.explore
            info.explore_id = req.explore_id
            info.times = int(st.get("times", 0))
            if not st.get("start_time"):
                rsp.status = StatusCode.StatusCode_EXPLORE_NOT_EXISTS
                session.send(MsgId.ExploreCancelRsp, rsp, packet_id)
                return
            st["start_time"] = 0
            st["is_quick_finish"] = False
            db.set_kv(
                session.player_id,
                "activity_explore",
                key,
                pickle.dumps(st),
            )
            info.start_time = 0
            session.send(MsgId.ExploreCancelRsp, rsp, packet_id)
            return

        e = garden_state.get_explore(session.player_id, req.explore_id)
        e["start_time"] = 0
        e["is_quick_finish"] = False
        garden_state.fill_explore_info(rsp.explore, req.explore_id, e)
        garden_state.set_explore(session.player_id, req.explore_id, e)

        session.send(MsgId.ExploreCancelRsp, rsp, packet_id)  # 1827,1828
