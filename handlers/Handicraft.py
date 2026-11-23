from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import random

from proto.net_pb2 import (
    HandicraftReq,
    HandicraftRsp,
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
    life_blob = db.get_life(player_id, LifeType.LIFE_TYPE_Handicraft)
    if life_blob:
        info = LifeBaseInfo()
        info.ParseFromString(life_blob)
        return max(info.level, 1)
    return 1


@packet_handler(MsgId.HandicraftReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = HandicraftReq()
        req.ParseFromString(data)

        rsp = HandicraftRsp()
        rsp.status = StatusCode.StatusCode_OK
        result = rsp.life_common_result
        result.life_type = LifeType.LIFE_TYPE_Handicraft
        result.is_success = False

        # 配方表 Handicraft.handicraft_item: {i_d, handicraft_level,
        recipe = None
        for e in res["Handicraft"]["handicraft_item"]["datas"]:
            if e.get("i_d") == req.handicraft_id:
                recipe = e
                break
        if not recipe:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.HandicraftRsp, rsp, packet_id)  # 1383,1384
            return

        # 手工等级校验(Handicraft.handicraft_item.handicraft_level vs 生活等级)
        if recipe.get("handicraft_level", 0) > _life_level(session.player_id):
            rsp.status = StatusCode.StatusCode_LifeLvNotEnough
            session.send(MsgId.HandicraftRsp, rsp, packet_id)  # 1383,1384
            return

        # 汇总消耗: 精力(need_item_i_d=11) + 材料(handicraft_items)
        needs = {}
        need_item_id = recipe.get("need_item_i_d")
        if need_item_id:
            needs[need_item_id] = needs.get(need_item_id, 0) + recipe.get(
                "need_item_count", 0
            )
        for m in recipe.get("handicraft_items", ()):
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
                session.send(MsgId.HandicraftRsp, rsp, packet_id)  # 1383,1384
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
            get_item_id = recipe.get("get_item_i_d", req.handicraft_id)
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
                    session.send(MsgId.HandicraftRsp, rsp, packet_id)  # 1383,1384
                    return
            item_mgr.mark_new_item(session.player_id, get_detail)
            db.set_item_detail(
                session.player_id, get_detail.SerializeToString(), get_item_id
            )
            # 生活图鉴计数
            db.incr_kv(session.player_id, "life_book", "4:" + str(get_item_id), 1)
            # 成就: 装饰品制作/加工材料/制作[成品](事件层归族)
            achieve_track.report(session, "craft_furniture", match=get_item_id)
            pack.items.add().CopyFrom(get_detail)
            get_detail.main_item.base_item.num = 1
            result.result_items.add().CopyFrom(get_detail)
        session.send(MsgId.PackNotice, pack, 0)  # 1400

        # 增加手工熟练度并推送通知
        life_blob = db.get_life(session.player_id, LifeType.LIFE_TYPE_Handicraft)
        if life_blob:
            info = LifeBaseInfo()
            info.ParseFromString(life_blob)
            info.proficiency_value += 10
            db.set_life(
                session.player_id,
                LifeType.LIFE_TYPE_Handicraft,
                info.SerializeToString(),
            )
            notice = LifeProficiencyNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.life_proficiency.life_type = LifeType.LIFE_TYPE_Handicraft
            notice.life_proficiency.proficiency_value = info.proficiency_value
            session.send(MsgId.LifeProficiencyNotice, notice, 0)  # 1368
            life_achieve.notify(session, LifeType.LIFE_TYPE_Handicraft)

        session.send(MsgId.HandicraftRsp, rsp, packet_id)  # 1383,1384
