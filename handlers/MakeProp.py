from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import random

from proto.net_pb2 import (
    MakePropReq,
    MakePropRsp,
    PackNotice,
    LifeProficiencyNotice,
    StatusCode,
    ItemDetail,
    LifeBaseInfo,
    LifeType,
)

import utils.db as db
import utils.life_achieve as life_achieve
from utils.res_loader import res
from utils.pb_create import make_item
from utils import achieve_track, item_mgr


def _load_detail(player_id, item_id):
    detail = ItemDetail()
    blob = db.get_item_detail(player_id, item_id)
    if blob:
        detail.ParseFromString(blob)
    else:
        make_item(item_id, 0, player_id, detail)
        if not detail.main_item.item_id:
            detail.main_item.item_id = item_id
    return detail


def _life_level(player_id):
    life_blob = db.get_life(player_id, LifeType.LIFE_TYPE_Making)
    if life_blob:
        info = LifeBaseInfo()
        info.ParseFromString(life_blob)
        return max(info.level, 1)
    return 1


@packet_handler(MsgId.MakePropReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MakePropReq()
        req.ParseFromString(data)

        rsp = MakePropRsp()
        rsp.status = StatusCode.StatusCode_OK
        result = rsp.life_common_result
        result.life_type = LifeType.LIFE_TYPE_Making
        result.is_success = False

        # 配方表 Make.make_item: {i_d, need_formula_item_i_d(需拥有配方物品),
        recipe = None
        for e in res["Make"]["make_item"]["datas"]:
            if e.get("i_d") == req.make_id:
                recipe = e
                break
        if not recipe:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.MakePropRsp, rsp, packet_id)  # 1381,1382
            return

        # 制作等级校验(Make.make_item.make_level vs 生活等级)
        if recipe.get("make_level", 0) > _life_level(session.player_id):
            rsp.status = StatusCode.StatusCode_LifeLvNotEnough
            session.send(MsgId.MakePropRsp, rsp, packet_id)  # 1381,1382
            return

        # 配方物品校验(need_formula_item_i_d, 682/699 条配方有此字段)
        formula_id = recipe.get("need_formula_item_i_d")
        if formula_id:
            formula = _load_detail(session.player_id, formula_id)
            if formula.main_item.base_item.num < 1:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH  # 未拥有配方
                session.send(MsgId.MakePropRsp, rsp, packet_id)  # 1381,1382
                return

        # 汇总消耗: 精力(need_item_i_d=11) + 材料(make_items)
        needs = {}
        need_item_id = recipe.get("need_item_i_d")
        if need_item_id:
            needs[need_item_id] = needs.get(need_item_id, 0) + recipe.get(
                "need_item_count", 0
            )
        for m in recipe.get("make_items", ()):
            if m.get("item_i_d"):
                needs[m["item_i_d"]] = needs.get(m["item_i_d"], 0) + m.get(
                    "item_count", 0
                )
        details = {}
        for item_id, count in needs.items():
            detail = _load_detail(session.player_id, item_id)
            if detail.main_item.base_item.num < count:
                if item_id == 11:
                    rsp.status = StatusCode.StatusCode_EnergyNotEnough
                else:
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.MakePropRsp, rsp, packet_id)  # 1381,1382
                return
            details[item_id] = detail

        # 扣除消耗(成功失败均扣; need_time 制作耗时未模拟, 即时完成)
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        for item_id, count in needs.items():
            detail = details[item_id]
            detail.main_item.base_item.num -= count
            db.set_item_detail(
                session.player_id, detail.SerializeToString(), item_id, None
            )
            pack.items.add().CopyFrom(detail)

        # 按 successful_probability 判定成败, 成功发放成品 get_item_i_d
        if random.random() < recipe.get("successful_probability", 1):
            result.is_success = True
            get_item_id = recipe.get("get_item_i_d", req.make_id)
            get_blob = db.get_item_detail(session.player_id, get_item_id)
            if get_blob:
                get_detail = ItemDetail()
                get_detail.ParseFromString(get_blob)
                get_detail.main_item.base_item.num += 1
            else:
                # 武器/防具子表缺配置时 make_item 会返回空 list 或抛异常, 须校验
                get_detail = make_item(get_item_id, 1, session.player_id)
                if not isinstance(get_detail, ItemDetail):
                    rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                    result.is_success = False
                    session.send(MsgId.PackNotice, pack, 0)  # 1400
                    session.send(MsgId.MakePropRsp, rsp, packet_id)  # 1381,1382
                    return
            item_mgr.mark_new_item(session.player_id, get_detail)
            db.set_item_detail(
                session.player_id, get_detail.SerializeToString(), get_item_id
            )
            pack.items.add().CopyFrom(get_detail)
            get_detail.main_item.base_item.num = 1
            result.result_items.add().CopyFrom(get_detail)
            # 生活图鉴计数
            if result.is_success:
                db.incr_kv(session.player_id, "life_book", "3:" + str(get_item_id), 1)
                # 成就: 成功制作 + 制作[成品](事件层归族)
                achieve_track.report(session, "craft_handmade", match=get_item_id)
        session.send(MsgId.PackNotice, pack, 0)  # 1400

        # 增加制作熟练度并推送通知
        life_blob = db.get_life(session.player_id, LifeType.LIFE_TYPE_Making)
        if life_blob:
            info = LifeBaseInfo()
            info.ParseFromString(life_blob)
            info.proficiency_value += 10
            db.set_life(
                session.player_id,
                LifeType.LIFE_TYPE_Making,
                info.SerializeToString(),
            )
            notice = LifeProficiencyNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.life_proficiency.life_type = LifeType.LIFE_TYPE_Making
            notice.life_proficiency.proficiency_value = info.proficiency_value
            session.send(MsgId.LifeProficiencyNotice, notice, 0)  # 1368
            life_achieve.notify(session, LifeType.LIFE_TYPE_Making)

        session.send(MsgId.MakePropRsp, rsp, packet_id)  # 1381,1382
