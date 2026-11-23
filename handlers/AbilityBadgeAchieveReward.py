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
注: 成就完成度不做服务端校验 —— 该类成就(如开箱数)的进度由 Achieve blob 计数,
但各成就的达成阈值在 MoonStone 表中无配置字段可对照, 私服放行由客户端把关
"""


@packet_handler(MsgId.AbilityBadgeAchieveRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbilityBadgeAchieveRewardReq()
        req.ParseFromString(data)

        rsp = AbilityBadgeAchieveRewardRsp()

        reward_list = []
        for achieve_id in req.achieve_ids:
            # achieve_id -> 所属 stone_reward_quest_data.i_d -> stone_area_data.item_i_d
            item_id = None
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
                        item_id = area.get("item_i_d")
                        break
            if not item_id:
                continue  # 非星符成就/配置缺失, 跳过
            # 成就须已达成(计数 >= Achieve.count_param), 未达成跳过
            _target = achieve_track.target_of(achieve_id)
            if (
                _target is not None
                and achieve_track.progress(session.player_id, achieve_id) < _target
            ):
                continue
            # 逐条原子去重(claimed_rewards 表持久化)
            if not db.try_claim(session.player_id, "badge_achieve", achieve_id):
                continue
            reward_list.append((item_id, 1))
            rsp.achieve_ids.append(achieve_id)

        if not reward_list:
            # 全部已领过(或均无配置)
            rsp.status = StatusCode.StatusCode_ABILITY_BADGE_ACHIEVE_REWARDED
            session.send(MsgId.AbilityBadgeAchieveRewardRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        item_mgr.grant_items(
            session.player_id, reward_list, rsp_items=rsp.items, session=session
        )

        # 成就: 解锁星符(每领取一枚计一次)
        achieve_track.report(session, "badge_reward", amount=len(reward_list) or 1)
        session.send(MsgId.AbilityBadgeAchieveRewardRsp, rsp, packet_id)  # 1637,1638
