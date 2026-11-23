from utils import refresh

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityQuestRewardReq,
    ActivityQuestRewardRsp,
    ItemDetail,
    StatusCode,
    PackNotice,
)
import utils.db as db
from utils.res_loader import res
from utils import achieve_track, item_mgr

"""
# 活动任务领奖 1991 1992(官方抓包 pack0/pack6.0 实证)
- is_progress=False: param = 活动第几天(days)，批量领取该天已完成且未领奖的条件。
- is_progress=True: param=进度档位 index, 奖励取
  activity_quest_reward(经 activity_quest.activity_quest_reward_i_d)的
  activity_quest_reward_item[{index, condition_item_i_d/num,
  reward_item_i_d/num}], condition_item 为进度代币(如 6001), 仅校验持有量不扣除。
- 普通任务响应不填reward_id；按活动与成就ID去重，同一天可分多次领取。
"""


def _quest_row(activity_id):
    if (
        "ActivityQuest" in res
        and "activity_quest" in res["ActivityQuest"]
        and "datas" in res["ActivityQuest"]["activity_quest"]
    ):
        for row in res["ActivityQuest"]["activity_quest"]["datas"]:
            if row.get("i_d") == activity_id:
                return row
    return None


def _progress_reward_row(reward_id):
    if (
        "ActivityQuest" in res
        and "activity_quest_reward" in res["ActivityQuest"]
        and "datas" in res["ActivityQuest"]["activity_quest_reward"]
    ):
        for row in res["ActivityQuest"]["activity_quest_reward"]["datas"]:
            if row.get("i_d") == reward_id:
                return row
    return None


@packet_handler(MsgId.ActivityQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityQuestRewardReq()
        req.ParseFromString(data)

        rsp = ActivityQuestRewardRsp()
        rsp.param = req.param
        rsp.is_progress = req.is_progress

        row = _quest_row(req.activity_id)
        if row is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ActivityQuestRewardRsp, rsp, packet_id)  # 1991,1992
            return

        rewards = None
        claimed_achieves = []
        if req.is_progress:
            # 进度档位奖励(activity_quest_reward)
            reward_row = _progress_reward_row(row.get("activity_quest_reward_i_d"))
            if reward_row is not None:
                for it in reward_row.get("activity_quest_reward_item", ()):
                    if it.get("index") != req.param:
                        continue
                    # 进度条件: 持有 condition_item_i_d 达 condition_item_num(不扣除)
                    cond_item = it.get("condition_item_i_d", 0)
                    cond_num = it.get("condition_item_num", 0)
                    if cond_item and cond_num:
                        raw = db.get_item_detail(session.player_id, cond_item)
                        have = 0
                        if raw:
                            detail = ItemDetail()
                            detail.ParseFromString(raw)
                            have = detail.main_item.base_item.num
                        if have < cond_num:
                            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                            session.send(
                                MsgId.ActivityQuestRewardRsp, rsp, packet_id
                            )  # 1991,1992
                            return
                    if it.get("reward_item_i_d") and it.get("reward_item_num", 0) > 0:
                        rewards = [(it["reward_item_i_d"], it["reward_item_num"])]
                    break
        else:
            # param 是活动第几天，一次领取该天全部已完成、未领取的任务。
            items = row.get("activity_quest_achieve_items", ())
            totals = {}
            if any(item.get("days") == req.param for item in items):
                rewards = []
                for item in items:
                    aid = item.get("achieve_i_d")
                    if item.get("days") != req.param or not aid:
                        continue
                    target = achieve_track.target_of(aid)
                    if (
                        target is None
                        or achieve_track.progress(session.player_id, aid) < target
                    ):
                        continue
                    if not db.try_claim(
                        session.player_id,
                        "activity_quest",
                        f"{req.activity_id}:achieve:{aid}",
                    ):
                        continue
                    claimed_achieves.append(aid)
                    for reward in item.get("activity_quest_item") or ():
                        item_id = reward.get("item_i_d")
                        count = reward.get("item_num", 0)
                        if item_id and count > 0:
                            totals[item_id] = totals.get(item_id, 0) + count
                rewards = list(totals.items())

        if rewards is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ActivityQuestRewardRsp, rsp, packet_id)  # 1991,1992
            return

        rsp.status = StatusCode.StatusCode_OK
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        if req.is_progress and not db.try_claim(
            session.player_id,
            "activity_quest",
            f"{req.activity_id}:progress:{req.param}",
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.ActivityQuestRewardRsp, rsp, packet_id)  # 1991,1992
            return
        if not req.is_progress and not claimed_achieves:
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.ActivityQuestRewardRsp, rsp, packet_id)
            return
        with achieve_track.batch(session):
            item_mgr.grant_items(
                session.player_id,
                rewards,
                rsp_items=rsp.rewards,
                pack_notice=pack,
                session=session,
            )
            session.send(MsgId.ActivityQuestRewardRsp, rsp, packet_id)
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
