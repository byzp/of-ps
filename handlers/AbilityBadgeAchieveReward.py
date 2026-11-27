from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AbilityBadgeAchieveRewardReq,
    AbilityBadgeAchieveRewardRsp,
    StatusCode,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils import achieve_track

"""
# 星云树奖励任务(星符成就)领奖 1637 1638
链路(已对表验证): MoonStone.stone_reward_quest_data.stone_reward_quest_data_group_info
{achieve_condition_i_d} 含 req 的 achieve_id, 经 stone_area_data.reward_quest_i_d
反查所属页, 发放该页的星符 stone_area_data.item_i_d x1
(如 achieve 50101010「开启补给箱20个」属 reward_quest 100/场景1 -> 星符·樱庭 301 x1;
文案佐证: String_Simplified「登陆了各种能够获得星符的奖励任务」, 单次数量表中无配置, 按 1 发放)。
领取状态持久化在 claimed_rewards 表(system='badge_achieve'), db.try_claim 逐条原子去重。
"""


def _badge_item_id(achieve_id):
    quest_table_id = None
    for entry in res["MoonStone"]["stone_reward_quest_data"]["datas"]:
        if not isinstance(entry, dict):
            continue
        for info in entry.get("stone_reward_quest_data_group_info", ()):
            if not isinstance(info, dict):
                continue
            if info.get("achieve_condition_i_d") == achieve_id:
                quest_table_id = entry["i_d"]
                break
        if quest_table_id is not None:
            break
    if quest_table_id is not None:
        for area in res["MoonStone"]["stone_area_data"]["datas"]:
            if not isinstance(area, dict):
                continue
            if area.get("reward_quest_i_d") == quest_table_id:
                return area.get("item_i_d")
    return None


@packet_handler(MsgId.AbilityBadgeAchieveRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbilityBadgeAchieveRewardReq()
        req.ParseFromString(data)

        rsp = AbilityBadgeAchieveRewardRsp()
        try:
            with item_mgr.player_lock(session.player_id), item_mgr.deferred_notifications(), db.transaction():
                candidates = []
                seen = set()
                for achieve_id in req.achieve_ids:
                    if achieve_id in seen:
                        continue
                    seen.add(achieve_id)
                    item_id = _badge_item_id(achieve_id)
                    if not item_id:
                        continue
                    target = achieve_track.target_of(achieve_id)
                    if target is not None and achieve_track.progress(session.player_id, achieve_id) < target:
                        continue
                    candidates.append((achieve_id, item_id))

                # 先验证整批奖励, 再写任何 claim; 中途发奖失败由事务整体回滚。
                rewards = [(item_id, 1) for _, item_id in candidates]
                item_mgr.validate_rewards(rewards)
                claimed = []
                for achieve_id, _ in candidates:
                    if db.try_claim(session.player_id, "badge_achieve", achieve_id):
                        claimed.append(achieve_id)
                        rsp.achieve_ids.append(achieve_id)
                if not claimed:
                    rsp.status = StatusCode.StatusCode_ABILITY_BADGE_ACHIEVE_REWARDED
                else:
                    item_mgr.grant_items(
                        session.player_id,
                        [(item_id, 1) for aid, item_id in candidates if aid in claimed],
                        rsp_items=rsp.items,
                        session=session,
                    )
                    rsp.status = StatusCode.StatusCode_OK
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.achieve_ids[:]
            del rsp.items[:]

        session.send(MsgId.AbilityBadgeAchieveRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            achieve_track.report(session, "badge_reward", amount=len(rsp.achieve_ids))
