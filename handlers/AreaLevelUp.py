from proto.net_pb2 import Achieve as _PbAchieve

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    Achieve,
    AreaLevelUpReq,
    AreaLevelUpRsp,
    StatusCode,
    AreaData,
)

import utils.db as db
from utils.res_loader import res
from utils import achieve_track

"""
# 区域升级 1905 1906
等级持久化在 areas 表的 AreaData blob(与 AreaUnlock 相同)。
等级上限来源 Area.json: area_data(i_d=场景) → area_data_group.area_level_i_d
→ area_level_data.area_level_data_group(level 1~5)。
升级条件: 当前等级 mission_pool_i_d → area_mission_data 的 achieve 条件
需在玩家成就表中有记录(count>0, 由区域任务完成时写入), 否则
AREA_LEVEL_QUEST_NOT_FINISH(与官方口径一致)。
Area.json 无升级消耗/奖励字段, 故不扣道具, rsp.items/achieves 留空。
"""


def _area_level_group(scene_id, area_id):
    """取区域的等级配置 area_level_data_group; 找不到返回 None"""
    area_datas = res.get("Area", {}).get("area_data", {}).get("datas")
    level_datas = res.get("Area", {}).get("area_level_data", {}).get("datas")
    if not isinstance(area_datas, (list, tuple)):
        return None
    if not isinstance(level_datas, (list, tuple)):
        return None

    entry = None
    for row in area_datas:  # 优先在当前场景的分组里找
        if row.get("i_d") == scene_id:
            for g in row.get("area_data_group", ()):
                if g.get("area_i_d") == area_id:
                    entry = g
                    break
            break
    if entry is None:
        for row in area_datas:
            for g in row.get("area_data_group", ()):
                if g.get("area_i_d") == area_id:
                    entry = g
                    break
            if entry is not None:
                break
    if entry is None:
        return None

    level_id = entry.get("area_level_i_d")
    for row in level_datas:
        if row.get("i_d") == level_id:
            return row.get("area_level_data_group", ())
    return None


@packet_handler(MsgId.AreaLevelUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AreaLevelUpReq()
        req.ParseFromString(data)

        rsp = AreaLevelUpRsp()

        area_b = db.get_area(session.player_id, session.scene_id, req.area_id)
        if not area_b:
            rsp.status = StatusCode.StatusCode_AREA_NOT_UNLOCK
            rsp.area.area_id = req.area_id
            session.send(MsgId.AreaLevelUpRsp, rsp, packet_id)
            return

        area = AreaData()
        area.ParseFromString(area_b)
        area.area_id = req.area_id
        area.area_state = AreaData.AreaState.Unlock

        # 升级条件校验: 当前等级的 mission_pool_i_d 对应 area_mission_data achieve 全部有进度
        mission_pool = None
        for g in res["Area"]["area_data"]["datas"]:
            hit = None
            for gg in g.get("area_data_group", ()):
                if gg.get("area_i_d") == req.area_id:
                    hit = gg
                    break
            if hit and hit.get("mission_pool_i_d"):
                mission_pool = hit["mission_pool_i_d"]
                break
        missions = next(
            (
                m
                for m in res["Area"]["area_mission_data"]["datas"]
                if m.get("i_d") == mission_pool
            ),
            None,
        )
        for mi in (missions or {}).get("area_mission_data_group", ()):
            cond_id = mi.get("achieve_condition_i_d")
            blob = db.get_achieve(session.player_id, cond_id)
            if not blob:
                rsp.status = StatusCode.StatusCode_AREA_LEVEL_QUEST_NOT_FINISH
                rsp.area.CopyFrom(area)
                session.send(MsgId.AreaLevelUpRsp, rsp, packet_id)
                return
            a = Achieve()
            a.ParseFromString(blob)
            if a.count <= 0:
                rsp.status = StatusCode.StatusCode_AREA_LEVEL_QUEST_NOT_FINISH
                rsp.area.CopyFrom(area)
                session.send(MsgId.AreaLevelUpRsp, rsp, packet_id)
                return

        group = _area_level_group(session.scene_id, req.area_id)
        if group:
            max_level = max(g.get("level", 0) for g in group)
            if max_level and area.level + 1 > max_level:
                rsp.status = StatusCode.StatusCode_AREA_LEVEL_LIMIT
                rsp.area.CopyFrom(area)
                session.send(MsgId.AreaLevelUpRsp, rsp, packet_id)
                return

        area.level += 1
        db.set_area(
            session.player_id,
            session.scene_id,
            req.area_id,
            area.SerializeToString(),
        )

        rsp.status = StatusCode.StatusCode_OK
        rsp.area.CopyFrom(area)

        _pool_id = None
        for _g in res.get("Area", {}).get("area_data", {}).get("datas") or ():
            for _gg in _g.get("area_data_group", ()) or ():
                if _gg.get("area_i_d") == req.area_id:
                    _pool_id = _gg.get("mission_pool_i_d")
                    break
            if _pool_id:
                break
        _missions = next(
            (
                _m
                for _m in res.get("Area", {}).get("area_mission_data", {}).get("datas")
                or ()
                if _m.get("i_d") == _pool_id
            ),
            None,
        )
        for _mi in (_missions or {}).get("area_mission_data_group", ()) or ():
            _cid = _mi.get("achieve_condition_i_d")
            if not _cid:
                continue
            _a = _PbAchieve()
            _a.achieve_id = _cid
            _blob = db.get_achieve(session.player_id, _cid)
            if _blob:
                _a.ParseFromString(_blob)
            rsp.achieves.add().CopyFrom(_a)

        # 成就140: 升级区域装置。
        achieve_track.report(session, "area_level_up")
        session.send(MsgId.AreaLevelUpRsp, rsp, packet_id)  # 1905,1906
