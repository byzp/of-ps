from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import random
from config import Config

from proto.net_pb2 import (
    CookingFoodReq,
    CookingFoodRsp,
    PackNotice,
    StatusCode,
    ItemDetail,
    LifeBaseInfo,
    LifeType,
    LifeProficiencyNotice,
)

import utils.db as db
import utils.life_achieve as life_achieve
from utils import item_mgr
from utils.res_loader import res
from utils.pb_create import make_item
from utils import achieve_track


def _life_level(player_id):
    life_blob = db.get_life(player_id, LifeType.LIFE_TYPE_Cooking)
    if life_blob:
        info = LifeBaseInfo()
        info.ParseFromString(life_blob)
        return max(info.level, 1)
    return 1


@packet_handler(MsgId.CookingFoodReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CookingFoodReq()
        req.ParseFromString(data)

        rsp = CookingFoodRsp()
        rsp.status = StatusCode.StatusCode_OK
        result = rsp.life_common_result
        result.life_type = LifeType.LIFE_TYPE_Cooking
        result.is_success = False

        # 配方表 Cooking.cook_food: {i_d, need_formula_item_i_d(68/89 条有),
        food = None
        for e in res.get("Cooking", {}).get("cook_food", {}).get("datas", ()) or ():
            if e.get("i_d") == req.food_id:
                food = e
                break
        if not food:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.CookingFoodRsp, rsp, packet_id)
            return

        # 烹饪等级校验(Cooking.cook_food.cook_level vs 生活等级)
        if food.get("cook_level", 0) > _life_level(session.player_id):
            rsp.status = StatusCode.StatusCode_LifeLvNotEnough
            session.send(MsgId.CookingFoodRsp, rsp, packet_id)
            return

        # 食谱物品校验(need_formula_item_i_d)
        formula_id = food.get("need_formula_item_i_d")
        if formula_id:
            if item_mgr.get_num(session.player_id, formula_id) < 1:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH  # 未拥有食谱
                session.send(MsgId.CookingFoodRsp, rsp, packet_id)
                return

        # 汇总消耗: 精力(need_item_i_d=11) + 食材(cook_food_items)
        needs = {}
        need_item_id = food.get("need_item_i_d")
        if need_item_id:
            needs[need_item_id] = needs.get(need_item_id, 0) + food.get(
                "need_item_count", 0
            )
        for ingredient in food.get("cook_food_items", ()):
            ing_id = ingredient.get("food_item_i_d")
            if ing_id:
                needs[ing_id] = needs.get(ing_id, 0) + ingredient.get(
                    "food_item_count", 0
                )

        # 整体校验: 任一物品不足则拒绝
        for item_id, count in needs.items():
            if item_mgr.get_num(session.player_id, item_id) < count:
                if item_id == 11:
                    rsp.status = StatusCode.StatusCode_EnergyNotEnough
                else:
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                session.send(MsgId.CookingFoodRsp, rsp, packet_id)
                return

        # 同一行为先响应，再统一推送成就和任务。
        with achieve_track.batch(session):
            self._cook(session, req, rsp, packet_id, food, needs)

    def _cook(self, session, req, rsp, packet_id, food, needs):
        result = rsp.life_common_result
        # 扣除消耗(成功失败均扣; need_time 烹饪耗时未模拟, 即时完成)
        cost_list = [(iid, cnt) for iid, cnt in needs.items()]
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        if not item_mgr.consume_items(
            session.player_id, cost_list, pack_notice=rsp1, session=session
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.CookingFoodRsp, rsp, packet_id)
            return

        # 按 successful_probability 判定成败, 成功发放成品 get_item_i_d
        if random.random() < food.get("successful_probability", 1):
            result.is_success = True
            get_item_id = food["get_item_i_d"]
            db.incr_kv(session.player_id, "life_book", "1:" + str(get_item_id), 1)
            item_mgr.grant_items(
                session.player_id,
                [(get_item_id, 1)],
                rsp_items=result.result_items,
                pack_notice=rsp1,
                session=session,
            )
            # result_items 里填 num=1 的获得量(展示用), 上面 grant_items 已处理
            # 成就: 烹饪成功一次上报(制作/菜谱成品/炉具由事件层归族)
            conditions = life_achieve.proficiency_conditions(
                LifeType.LIFE_TYPE_Cooking, _life_level(session.player_id)
            )
            previous = {
                entry["achieve_condition_i_d"]: achieve_track.progress(
                    session.player_id, entry["achieve_condition_i_d"]
                )
                for entry in conditions
            }
            achieve_track.report(
                session,
                "cook",
                recipe=get_item_id,
                tool=3 if req.has_camp_fire else 2,
            )

            life_blob = db.get_life(session.player_id, LifeType.LIFE_TYPE_Cooking)
            if life_blob:
                info = LifeBaseInfo()
                info.ParseFromString(life_blob)
                info.proficiency_value += life_achieve.proficiency_gain(
                    session.player_id, conditions, previous
                )
                db.set_life(
                    session.player_id,
                    LifeType.LIFE_TYPE_Cooking,
                    info.SerializeToString(),
                )
                prof_notice = LifeProficiencyNotice()
                prof_notice.status = StatusCode.StatusCode_OK
                prof_notice.life_proficiency.life_type = LifeType.LIFE_TYPE_Cooking
                prof_notice.life_proficiency.proficiency_value = info.proficiency_value
                session.send(MsgId.LifeProficiencyNotice, prof_notice, 0)
        else:
            # 成就: 烹饪失败
            achieve_track.report(session, "cook_fail")
            # 失败: 材料已扣, result_items 列出损失的食材供客户端展示
            for ingredient in food.get("cook_food_items", ()):
                ing_id = ingredient.get("food_item_i_d", 0)
                ing_count = ingredient.get("food_item_count", 0)
                ing_detail = make_item(ing_id, ing_count, session.player_id)
                if isinstance(ing_detail, ItemDetail):
                    result.result_items.add().CopyFrom(ing_detail)

        session.send(MsgId.CookingFoodRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
        # 教学条件168由成功烹饪事件统一计数；失败不能完成教学任务。
