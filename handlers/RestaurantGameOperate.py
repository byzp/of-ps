from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import random

from proto.net_pb2 import (
    RestaurantGameOperateReq,
    RestaurantGameOperateRsp,
    RestaurantGameOperateType,
    StatusCode,
    PackNotice,
)

from utils import restaurant_game_store as store
from utils import item_mgr as items_util


@packet_handler(MsgId.RestaurantGameOperateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = RestaurantGameOperateReq()
        req.ParseFromString(data)

        rsp = RestaurantGameOperateRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.activity_id = req.activity_id
        coin_item = store.get_coin_item_id(req.activity_id)
        notice = None  # 货币变动时推 PackNotice
        changed = []  # [(index, food)]
        # 餐厅格子状态为玩家私有, handler 为单线程执行, 不需要全局锁
        if True:
            state = store.get_state(session.player_id, req.activity_id)
            grids = state["grids"]
            bag_cfgs = {
                b.get("bag_i_d"): b for b in store.get_desk_bags(req.activity_id)
            }

            def unlocked(i):
                return store.grid_unlocked(state, bag_cfgs.get(i, {}))

            if req.type == RestaurantGameOperateType.RestaurantGameOperateType_Buy:
                # 购买: restaurant_random_pool[buy_pool_id] 随机产 1 个食物,
                # 消耗小游戏金币 rate_min~rate_max
                pool = store.get_pool_cfg(req.activity_id, req.buy_pool_id)
                foods = [
                    g["food_id"]
                    for g in (pool or {}).get("restaurant_random_pool_group_info", ())
                    if g.get("food_id")
                ]
                target = 0
                for index in sorted(grids):
                    if grids[index] == 0 and unlocked(index):
                        target = index
                        break
                if not pool or not foods:
                    rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                elif not target:
                    rsp.status = StatusCode.StatusCode_FAIL  # 没有可用空格子
                else:
                    cost = random.randint(
                        pool.get("rate_min", 0),
                        max(pool.get("rate_max", 0), pool.get("rate_min", 0)),
                    )
                    notice = PackNotice()
                    notice.status = StatusCode.StatusCode_OK
                    if cost and not items_util.consume_items(
                        session.player_id,
                        [(coin_item, cost)],
                        pack_notice=notice,
                        session=session,
                    ):
                        rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                        notice = None
                    else:
                        food = random.choice(foods)
                        grids[target] = food
                        changed.append((target, food))
            elif req.type == RestaurantGameOperateType.RestaurantGameOperateType_Mix:
                # 合成: 相同食物合成 restaurant_game_food.synthetic_target
                # 格子必须去重, 否则重复格子(如 [5,5])可用单个食物免费合成
                foods = [grids.get(i, 0) for i in req.grid]
                food_cfg = (
                    store.get_food_cfg(req.activity_id, foods[0]) if foods else None
                )
                result = food_cfg.get("synthetic_target", 0) if food_cfg else 0
                if not (
                    len(set(req.grid)) == len(req.grid)
                    and len(req.grid) >= 2
                    and all(unlocked(i) for i in req.grid)
                    and all(f == foods[0] for f in foods)
                    and foods[0] > 0
                ):
                    rsp.status = StatusCode.StatusCode_BAD_REQ
                elif not result:
                    # 满级食物(5 级 / 特殊 103)无 synthetic_target, 无法再合成
                    rsp.status = (
                        StatusCode.StatusCode_MINIGAME_RESTAURANT_FOOD_MAX_LEVEL
                    )
                else:
                    # 概率合成出特殊食物(synthesis_special_food_i_d, 如 101):
                    special = food_cfg.get("synthesis_special_food_i_d", 0)
                    if special:
                        if random.randint(1, 100) <= state["special_weight"]:
                            result = special
                            state["special_weight"] = store.get_global_int(
                                "RestaurantGameBaseWeight", 10
                            )
                        else:
                            state["special_weight"] = min(
                                state["special_weight"]
                                + store.get_global_int("RestaurantGameWeightNumber", 3),
                                store.get_global_int("RestaurantGameWeightLimit", 90),
                            )
                    for i in req.grid:
                        grids[i] = 0
                        changed.append((i, 0))
                    target = req.grid[-1]
                    grids[target] = result
                    changed[-1] = (target, result)
            elif (
                req.type == RestaurantGameOperateType.RestaurantGameOperateType_Recycle
            ):
                # 回收: 清空格子, 按 restaurant_game_food.recycling_price_min/max
                # 返还小游戏金币
                refund = 0
                for i in req.grid:
                    food = grids.get(i, 0)
                    if food and unlocked(i):
                        cfg = store.get_food_cfg(req.activity_id, food)
                        if cfg:
                            lo = cfg.get("recycling_price_min", 0)
                            hi = max(cfg.get("recycling_price_max", 0), lo)
                            refund += random.randint(lo, hi)
                        grids[i] = 0
                        changed.append((i, 0))
                if refund:
                    notice = PackNotice()
                    notice.status = StatusCode.StatusCode_OK
                    items_util.grant_items(
                        session.player_id,
                        [(coin_item, refund)],
                        rsp_items=rsp.item_details,
                        pack_notice=notice,
                        session=session,
                    )
        for index, food in changed:
            grid = rsp.grid.add()
            grid.index = index
            grid.food = food
            grid.is_un_lock = True
        store.save_state(session.player_id, req.activity_id, state)
        session.send(MsgId.RestaurantGameOperateRsp, rsp, packet_id)  # 2733,2734
        if notice is not None:
            session.send(MsgId.PackNotice, notice, 0)  # 1400
