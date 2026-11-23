from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    LifeLeveUpReq,
    LifeLeveUpRsp,
    StatusCode,
    LifeBaseInfo,
    LifeType,
    ItemDetail,
    PackNotice,
)

import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item
from utils import achieve_track


def _level_cfg(life_type, level):
    """返回 (当前等级行, 表内最大等级); 表缺失返回 (None, None)。
    LifeGather.life_gather 仅一行(i_d=1, 阈值10000, 无消耗/上限), 任意等级套用"""
    m = Config.LIFE_LEVE_UP_LEVEL_TABLES.get(life_type)
    if not m:
        return None, None
    fname, tname, _ = m
    if not (fname in res and tname in res[fname] and "datas" in res[fname][tname]):
        return None, None
    datas = res[fname][tname]["datas"]
    if not datas:
        return None, None
    max_id = max(e.get("i_d", 0) for e in datas)
    if len(datas) == 1:  # LifeGather 单行通用
        return datas[0], None
    for e in datas:
        if e.get("i_d") == level:
            return e, max_id
    return None, None


@packet_handler(MsgId.LifeLeveUpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = LifeLeveUpReq()
        req.ParseFromString(data)

        rsp = LifeLeveUpRsp()
        rsp.status = StatusCode.StatusCode_OK

        # life_type=0 时 db.get_life 返回整个 dict 而非 bytes; 生活类型仅初始化 1~6, 越界会 KeyError
        if not 1 <= req.life_type <= 6:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.LifeLeveUpRsp, rsp, packet_id)  # 1389,1390
            return

        info = LifeBaseInfo()
        life_blob = db.get_life(session.player_id, req.life_type)
        if not life_blob:
            info.life_type = req.life_type
            info.level = 2
            rsp.life_base_info.CopyFrom(info)
            session.send(MsgId.LifeLeveUpRsp, rsp, packet_id)  # 1389,1390
            return

        info.ParseFromString(life_blob)
        cur_level = max(info.level, 1)
        cfg, max_level = _level_cfg(req.life_type, cur_level)

        if cfg is not None:
            # 满级校验(等级表 i_d 1~10, 末级行无升级消耗字段)
            if max_level and cur_level >= max_level:
                rsp.status = StatusCode.StatusCode_LifeMaxLv
                rsp.life_base_info.CopyFrom(info)
                session.send(MsgId.LifeLeveUpRsp, rsp, packet_id)  # 1389,1390
                return
            # 熟练度校验(upgrade_level_by_proficiency, 通常每级 10000)
            need_prof = cfg.get("upgrade_level_by_proficiency", 0)
            if info.proficiency_value < need_prof:
                rsp.status = StatusCode.StatusCode_ProficiencyNotEnough
                rsp.life_base_info.CopyFrom(info)
                session.send(MsgId.LifeLeveUpRsp, rsp, packet_id)  # 1389,1390
                return
            # 升级消耗(如 Make.make_level 1级→2级: 金币101 x1000)
            prefix = Config.LIFE_LEVE_UP_LEVEL_TABLES[req.life_type][2]
            cost_item_id = cfg.get(prefix + "_i_d")
            cost_count = cfg.get(prefix + "_count", 0)
            if cost_item_id and cost_count:
                cost_detail = ItemDetail()
                cost_b = db.get_item_detail(session.player_id, cost_item_id)
                if cost_b:
                    cost_detail.ParseFromString(cost_b)
                else:
                    make_item(cost_item_id, 0, session.player_id, cost_detail)
                if cost_detail.main_item.base_item.num < cost_count:
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    rsp.life_base_info.CopyFrom(info)
                    session.send(MsgId.LifeLeveUpRsp, rsp, packet_id)  # 1389,1390
                    return
                cost_detail.main_item.base_item.num -= cost_count
                db.set_item_detail(
                    session.player_id,
                    cost_detail.SerializeToString(),
                    cost_item_id,
                    None,
                )
                pack = PackNotice()
                pack.status = StatusCode.StatusCode_OK
                pack.items.add().CopyFrom(cost_detail)
                session.send(MsgId.PackNotice, pack, 0)
            # 升级并扣减本级熟练度(表阈值按级配置, 视为逐级消耗)
            info.level = cur_level + 1
            info.proficiency_value = max(info.proficiency_value - need_prof, 0)
        else:
            info.level = cur_level + 1

        db.set_life(session.player_id, req.life_type, info.SerializeToString())
        rsp.life_base_info.CopyFrom(info)
        if req.life_type == 1:
            achieve_track.report(session, "life_level")
        session.send(MsgId.LifeLeveUpRsp, rsp, packet_id)  # 1389,1390
