import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    RestaurantGameQuestRewardReq,
    RestaurantGameQuestRewardRsp,
    QuestStatus,
    StatusCode,
    PackNotice,
)

from utils import restaurant_game_store as store
from utils import item_mgr
from utils import refresh


@packet_handler(MsgId.RestaurantGameQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = RestaurantGameQuestRewardReq()
        req.ParseFromString(data)

        rsp = RestaurantGameQuestRewardRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.activity_id = req.activity_id

        cfg = store.get_quests(req.activity_id).get(req.quest_id)
        if not cfg:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(
                MsgId.RestaurantGameQuestRewardRsp, rsp, packet_id
            )  # 2739,2740
            return

        # 餐厅状态为玩家私有, handler 单线程执行, 不需要全局锁
        state = store.get_state(session.player_id, req.activity_id)
        # 类型 1(is_refresh 日常任务): 每日刷新, 不进入永久已领集合
        is_refresh = bool(cfg.get("is_refresh"))
        day = str(refresh.day_index())
        if is_refresh:
            state.setdefault("refresh_claimed", {})
            state["rewarded_quests"].discard(req.quest_id)

        if req.quest_id in state["rewarded_quests"]:
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
        elif (
            not cfg.get("new_restaurant_game_quest_type")
            and cfg.get("param") not in state["completed"]
        ):
            # 通关任务(类型缺省 0): param = 目标关卡 id, 未通关不可领
            rsp.status = StatusCode.StatusCode_FAIL
        elif is_refresh and (f"{req.quest_id}:{day}" in state["refresh_claimed"]):
            # 日常任务当日已领取
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
        else:
            if is_refresh:
                state["refresh_claimed"][f"{req.quest_id}:{day}"] = day
                # 清理过期日键
                for k in [k for k, v in state["refresh_claimed"].items() if v != day]:
                    del state["refresh_claimed"][k]
            else:
                state["rewarded_quests"].add(req.quest_id)
        store.save_state(session.player_id, req.activity_id, state)

        notice = None
        if rsp.status == StatusCode.StatusCode_OK:
            # 任务奖励: restaurant_game_quest 的
            # game_coin_i_d x game_coin(1601 小游戏金币) +
            rewards = []
            if cfg.get("game_coin_i_d") and cfg.get("game_coin"):
                rewards.append((cfg["game_coin_i_d"], cfg["game_coin"]))
            if cfg.get("game_integral_item") and cfg.get("game_integral"):
                rewards.append((cfg["game_integral_item"], cfg["game_integral"]))
            notice = PackNotice()
            notice.status = StatusCode.StatusCode_OK
            item_mgr.grant_items(
                session.player_id,
                rewards,
                rsp_items=rsp.item_details,
                pack_notice=notice,
                session=session,
            )

        rsp.quest.quest_id = req.quest_id
        if rsp.status in (
            StatusCode.StatusCode_OK,
            StatusCode.StatusCode_REPEAT_GET_REWARD,
        ):
            rsp.quest.status = QuestStatus.QuestStatus_Finish
        else:
            rsp.quest.status = QuestStatus.QuestStatus_InProgress
        session.send(MsgId.RestaurantGameQuestRewardRsp, rsp, packet_id)  # 2739,2740
        if notice is not None:
            session.send(MsgId.PackNotice, notice, 0)  # 1400
