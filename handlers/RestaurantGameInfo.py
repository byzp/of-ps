from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    RestaurantGameInfoReq,
    RestaurantGameInfoRsp,
    QuestStatus,
    StatusCode,
)

from utils import restaurant_game_store as store


def fill_dungeon_info(info, state):
    """填充 RestaurantGameDungeonInfo 的关卡与顾客"""
    info.dungeon_id = state["dungeon_id"]
    for customer_index, c in state["customers"].items():
        cu = info.customer_list.add()
        cu.customer_index = customer_index
        cu.food = c["food"]
        cu.status = c["status"]


@packet_handler(MsgId.RestaurantGameInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = RestaurantGameInfoReq()
        req.ParseFromString(data)

        rsp = RestaurantGameInfoRsp()
        rsp.activity_id = req.activity_id
        if not store.get_desk_bags(req.activity_id) and not store.get_quests(
            req.activity_id
        ):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.RestaurantGameInfoRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        # 状态为内存态(见 utils/restaurant_game_store), 配置来自 RestaurantGame.json
        state = store.get_state(session.player_id, req.activity_id)
        bags = store.get_desk_bags(req.activity_id)
        bag_cfgs = {b.get("bag_i_d"): b for b in bags}
        for index, food in state["grids"].items():
            grid = rsp.grid_list.add()
            grid.index = index
            grid.food = food
            # 格子解锁: restaurant_desk_bag.unlock_dungon_i_d(需通关对应关卡)
            grid.is_un_lock = store.grid_unlocked(state, bag_cfgs.get(index, {}))
        fill_dungeon_info(rsp.dungeon_info, state)
        # 任务: restaurant_game_quest, 已领取=Finish,
        # 通关任务(param=关卡 id)已达成=Completed, 其余=InProgress
        for quest_id, cfg in sorted(store.get_quests(req.activity_id).items()):
            q = rsp.dungeon_info.question_info.add()
            q.quest_id = quest_id
            if quest_id in state["rewarded_quests"]:
                q.status = QuestStatus.QuestStatus_Finish
            elif (
                not cfg.get("new_restaurant_game_quest_type")
                and cfg.get("param") in state["completed"]
            ):
                q.status = QuestStatus.QuestStatus_Completed
            else:
                q.status = QuestStatus.QuestStatus_InProgress
        session.send(MsgId.RestaurantGameInfoRsp, rsp, packet_id)  # 2731,2732
