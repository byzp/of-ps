from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import RestaurantGameEatReq, RestaurantGameEatRsp, StatusCode

from utils import restaurant_game_store as store
from handlers.RestaurantGameInfo import fill_dungeon_info


@packet_handler(MsgId.RestaurantGameEatReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = RestaurantGameEatReq()
        req.ParseFromString(data)

        rsp = RestaurantGameEatRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.activity_id = req.activity_id
        rsp.customer_index = req.customer_index
        state = store.get_state(session.player_id, req.activity_id)
        grids = state["grids"]
        customer = state["customers"].get(req.customer_index)
        # 校验: 顾客存在未完成, 且上的菜与订单食物一致
        # (订单 = restaurant_dungeon 关卡配置的 food_type+food_level 具体化)
        if (
            customer is None
            or customer["status"]
            or grids.get(req.grid, 0) != customer["food"]
        ):
            rsp.status = StatusCode.StatusCode_BAD_REQ
        else:
            # 上菜: 清空格子, 订单剩余份数-1, 归零后该顾客完成
            grids[req.grid] = 0
            grid = rsp.grid.add()
            grid.index = req.grid
            grid.food = 0
            grid.is_un_lock = True
            customer["remain"] -= 1
            if customer["remain"] <= 0:
                customer["status"] = True
            # 供餐本身无奖励字段(RestaurantGameEatRsp 无 item_details,
            # restaurant_game_food 亦无供餐价格), 收益来自任务奖励与回收;
            store.advance_if_cleared(state, req.activity_id)
        fill_dungeon_info(rsp.dungeon_info, state)
        store.save_state(session.player_id, req.activity_id, state)
        session.send(MsgId.RestaurantGameEatRsp, rsp, packet_id)  # 2735,2736
