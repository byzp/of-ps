import logging
import random

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    SewingReq,
    SewingRsp,
    PackNotice,
    LifeProficiencyNotice,
    LifeBaseInfo,
    LifeType,
    StatusCode,
    ItemDetail,
)

import utils.db as db
import utils.life_achieve as life_achieve
from utils import achieve_track, item_mgr
from utils.pb_create import make_item
from utils.res_loader import res

logger = logging.getLogger(__name__)


def _life_level(player_id):
    """当前纺织生活等级(无记录按 1)"""
    life_blob = db.get_life(player_id, LifeType.LIFE_TYPE_Sewing)
    if life_blob and isinstance(life_blob, (bytes, bytearray)):
        info = LifeBaseInfo()
        info.ParseFromString(life_blob)
        return max(info.level, 1)
    return 1


"""
# 纺织(缝纫) 1385 1386 —— 配方表 Spin.spin_item(纺织=Spin)
# {i_d, spin_level, need_item_i_d/need_item_count(精力11),
#  spin_items(材料), successful_probability, get_item_i_d(成品)}
# 行为与早期烹饪/手工艺同口径:
#   校验配方 → 等级 → 汇总精力+材料 → 扣耗(PackNotice) →
#   按概率判定成败 → 成功发放成品并计入图鉴/成就 → 熟练度+10 推送
"""


@packet_handler(MsgId.SewingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SewingReq()
        req.ParseFromString(data)

        rsp = SewingRsp()
        rsp.status = StatusCode.StatusCode_OK
        result = rsp.life_common_result
        result.life_type = LifeType.LIFE_TYPE_Sewing
        result.is_success = False

        # 查配方
        recipe = None
        for e in res["Spin"]["spin_item"]["datas"]:
            if e.get("i_d") == req.sewing_id:
                recipe = e
                break
        if not recipe:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.SewingRsp, rsp, packet_id)  # 1385,1386
            return

        # 纺织等级校验(spin_level vs 生活等级)
        if recipe.get("spin_level", 0) > _life_level(session.player_id):
            rsp.status = StatusCode.StatusCode_LifeLvNotEnough
            session.send(MsgId.SewingRsp, rsp, packet_id)
            return

        # 汇总消耗: 精力(need_item_i_d=11) + 材料(spin_items)
        needs = {}
        need_item_id = recipe.get("need_item_i_d")
        if need_item_id:
            needs[need_item_id] = needs.get(need_item_id, 0) + recipe.get(
                "need_item_count", 0
            )
        for m in recipe.get("spin_items", ()):
            if m.get("item_i_d"):
                needs[m["item_i_d"]] = needs.get(m["item_i_d"], 0) + m.get(
                    "item_count", 0
                )
        details = {}
        for item_id, count in needs.items():
            blob = db.get_item_detail(session.player_id, item_id)
            detail = ItemDetail()
            if blob and isinstance(blob, (bytes, bytearray)):
                detail.ParseFromString(blob)
            else:
                made = make_item(item_id, 0, session.player_id)
                detail = made if isinstance(made, ItemDetail) else detail
            if detail.main_item.base_item.num < count:
                logger.info(
                    "sewing short: need %s x%s, have %s",
                    item_id,
                    count,
                    detail.main_item.base_item.num,
                )
                if item_id == 11:
                    rsp.status = StatusCode.StatusCode_EnergyNotEnough
                else:
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.SewingRsp, rsp, packet_id)  # 1385,1386
                return
            details[item_id] = detail

        # 扣除消耗(成功失败均扣; need_time 织造耗时不延迟下发, 即时完成)
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
        if random.random() < float(recipe.get("successful_probability", 1)):
            result.is_success = True
            get_item_id = recipe.get("get_item_i_d", req.sewing_id)
            get_blob = db.get_item_detail(session.player_id, get_item_id)
            if get_blob:
                get_detail = ItemDetail()
                get_detail.ParseFromString(get_blob)
                get_detail.main_item.base_item.num += 1
            else:
                # 时装子表缺配置时 make_item 可能异常, 须校验
                get_detail = make_item(get_item_id, 1, session.player_id)
                if not isinstance(get_detail, ItemDetail):
                    rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                    session.send(MsgId.PackNotice, pack, 0)  # 1400
                    session.send(MsgId.SewingRsp, rsp, packet_id)
                    return
            item_mgr.mark_new_item(session.player_id, get_detail)
            db.set_item_detail(
                session.player_id, get_detail.SerializeToString(), get_item_id
            )
            pack.items.add().CopyFrom(get_detail)
            get_detail.main_item.base_item.num = 1
            result.result_items.add().CopyFrom(get_detail)
            # 生活图鉴计数
            db.incr_kv(session.player_id, "life_book", "5:" + str(get_item_id), 1)
            # 成就: 成功织造/纺织加工/制作[成品](事件层归族)
            achieve_track.report(session, "craft_sewing", match=get_item_id)

        session.send(MsgId.PackNotice, pack, 0)

        life_blob = db.get_life(session.player_id, LifeType.LIFE_TYPE_Sewing)
        if life_blob and isinstance(life_blob, (bytes, bytearray)):
            info = LifeBaseInfo()
            info.ParseFromString(life_blob)
            info.proficiency_value += 10
            db.set_life(
                session.player_id,
                LifeType.LIFE_TYPE_Sewing,
                info.SerializeToString(),
            )
            notice = LifeProficiencyNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.life_proficiency.life_type = LifeType.LIFE_TYPE_Sewing
            notice.life_proficiency.proficiency_value = info.proficiency_value
            session.send(MsgId.LifeProficiencyNotice, notice, 0)  # 1368
            life_achieve.notify(session, LifeType.LIFE_TYPE_Sewing)

        session.send(MsgId.SewingRsp, rsp, packet_id)  # 1385,1386
