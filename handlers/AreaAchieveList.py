from proto.net_pb2 import Achieve as PbAchieve

from proto.net_pb2 import AreaData

import utils.db as db

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import AreaAchieveListReq, AreaAchieveListRsp, StatusCode

from utils.res_loader import res

"""
# 区域成就列表 1907 1908
"""


def _valid_area_ids():
    ids = set()
    for e in res.get("Area", {}).get("area_data", {}).get("datas", ()) or ():
        for g in e.get("area_data_group") or ():
            if g.get("area_id"):
                ids.add(g["area_id"])
    return ids


@packet_handler(MsgId.AreaAchieveListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaAchieveListReq()
        req.ParseFromString(data)

        rsp = AreaAchieveListRsp()

        if req.area_id not in _valid_area_ids():
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.AreaAchieveListRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        rsp.area_id = req.area_id

        # 区域任务成就进度: area_level_data(area_id)[当前等级].mission_pool_i_d
        # -> area_mission_data.achieve_condition_i_d -> achieve 表真实计数

        level = 1
        area_b = db.get_area(session.player_id, session.scene_id, req.area_id)
        if area_b:
            ad = AreaData()
            ad.ParseFromString(area_b)
            level = ad.level if ad.level else 1
        pool_id = None
        row = next(
            (
                r
                for r in res.get("Area", {}).get("area_level_data", {}).get("datas", ())
                or ()
                if r.get("i_d") == req.area_id
            ),
            None,
        )
        if row:
            g = next(
                (
                    g
                    for g in row.get("area_level_data_group", ()) or ()
                    if g.get("level") == level
                ),
                None,
            )
            if g:
                pool_id = g.get("mission_pool_i_d")
        cond_ids = []
        missions = (
            next(
                (
                    m
                    for m in res.get("Area", {})
                    .get("area_mission_data", {})
                    .get("datas", ())
                    or ()
                    if m.get("i_d") == pool_id
                ),
                None,
            )
            if pool_id
            else None
        )
        for mi in (missions or {}).get("area_mission_data_group", ()):
            cid = mi.get("achieve_condition_i_d")
            if cid:
                cond_ids.append(cid)

        for cid in cond_ids:
            a = PbAchieve()
            a.achieve_id = cid
            blob = db.get_achieve(session.player_id, cid)
            if blob:
                a.ParseFromString(blob)
            rsp.achieves.add().CopyFrom(a)

        session.send(MsgId.AreaAchieveListRsp, rsp, packet_id)
