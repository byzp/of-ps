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
    LifeType,
)

import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item
from utils.pb_create import make_QuestNotice


@packet_handler(MsgId.CookingFoodReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = CookingFoodReq()
        req.ParseFromString(data)

        rsp = CookingFoodRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        result = rsp.life_common_result
        result.life_type = LifeType.LIFE_TYPE_Cooking
        for food in res["Cooking"]["cook_food"]["datas"]:
            if food["i_d"] == req.food_id:
                need_item_id = food["need_item_i_d"]
                need_count = food["need_item_count"]
                need_blob = db.get_item_detail(session.player_id, need_item_id)
                if need_blob:
                    need_detail = ItemDetail()
                    need_detail.ParseFromString(need_blob)
                else:
                    need_detail = make_item(need_item_id, 0, session.player_id)
                if need_detail.main_item.base_item.num < need_count:
                    rsp.status = StatusCode.StatusCode_EnergyNotEnough
                    session.send(MsgId.CookingFoodRsp, rsp, packet_id)
                    return
                need_detail.main_item.base_item.num -= need_count
                rsp1.items.add().CopyFrom(need_detail)
                db.set_item_detail(
                    session.player_id,
                    need_detail.SerializeToString(),
                    need_item_id,
                )
                if random.random() < food["successful_probability"]:
                    result.is_success = True
                    for ingredient in food.get("cook_food_items", []):
                        ing_id = ingredient.get("food_item_i_d", 0)
                        ing_count = ingredient.get("food_item_count", 0)
                        ing_blob = db.get_item_detail(session.player_id, ing_id)
                        if ing_blob:
                            ing_detail = ItemDetail()
                            ing_detail.ParseFromString(ing_blob)
                        else:
                            ing_detail = make_item(ing_id, 0, session.player_id)
                        ing_detail.main_item.base_item.num -= ing_count
                        rsp1.items.add().CopyFrom(ing_detail)
                        db.set_item_detail(
                            session.player_id,
                            ing_detail.SerializeToString(),
                            ing_id,
                        )
                    get_item_id = food["get_item_i_d"]
                    get_blob = db.get_item_detail(session.player_id, get_item_id)
                    if get_blob:
                        get_detail = ItemDetail()
                        get_detail.ParseFromString(get_blob)
                        get_detail.main_item.base_item.num += 1
                    else:
                        get_detail = make_item(get_item_id, 1, session.player_id)
                    rsp1.items.add().CopyFrom(get_detail)
                    db.set_item_detail(
                        session.player_id,
                        get_detail.SerializeToString(),
                        get_item_id,
                        None,
                    )
                    get_detail.main_item.base_item.num = 1
                    result.result_items.add().CopyFrom(get_detail)
                else:
                    result.is_success = False  # TODO 失败扣除一些物品
                    for ingredient in food.get("cook_food_items", []):
                        ing_id = ingredient.get("food_item_i_d", 0)
                        ing_count = ingredient.get("food_item_count", 0)
                        ing_detail = make_item(ing_id, ing_count, session.player_id)
                        result.result_items.add().CopyFrom(ing_detail)
                break

        session.send(MsgId.PackNotice, rsp1, 0)
        session.send(MsgId.CookingFoodRsp, rsp, packet_id)
        if not Config.SKIP_QUESTS and session.quests.get(100086) != None:
            rsp1 = make_QuestNotice(session, [11000861])
            if rsp1:
                session.send(MsgId.QuestNotice, rsp1, 0)
