from config import Config
from utils import quest_track as _qt

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ClaimQuestRewardReq,
    ClaimQuestRewardRsp,
    StatusCode,
    Chapter,
    PackNotice,
    Quest,
    QuestStatus,
)

import utils.db as db
from utils.res_loader import res
from utils import achieve_track, item_mgr
from utils.reward_resolver import resolve_reward


def _player_level(player_id):
    row = db.get_players_info(player_id, "level")
    return row[0] if row else 0


def _required_rewards(reward_id, level):
    """0/哨兵表示权威配置明确无奖励; 非零配置必须能解析出合法奖励。"""
    if not reward_id or reward_id == Config.NONE_REWARD:
        return []
    rewards = resolve_reward(reward_id, level)
    if not rewards:
        raise item_mgr.EconomyConfigError("missing quest reward config")
    item_mgr.validate_rewards(rewards)
    return rewards


def _chain_tail_echo(player_id, head_id):
    """引导链回显: 从链头沿 Quest 表相邻同名任务走到最后一个有存储的环,
    返回其存储状态(官方回包 complete_count 至少 1)。"""
    qd = [
        r
        for r in res["Quest"]["quest"]["datas"]
        if isinstance(r, dict) and r.get("i_d")
    ]
    idx = {r["i_d"]: i for i, r in enumerate(qd)}
    by = {r["i_d"]: r for r in qd}
    tail = head_id
    while True:
        i = idx.get(tail)
        if i is None or i + 1 >= len(qd):
            break
        if not by[tail].get("quest_group") or qd[i + 1].get("quest_group") != by[
            tail
        ].get("quest_group"):
            break
        if not db.get_quest(player_id, qd[i + 1]["i_d"]):
            break
        tail = qd[i + 1]["i_d"]
    q = Quest()
    blob = db.get_quest(player_id, tail)
    if blob:
        q.ParseFromString(blob)
    q.quest_id = tail
    if q.complete_count == 0:
        q.complete_count = 1
    return q


def _quest_conditions(quest_cfg):
    """任务条件成就 id 列表(condition_set_group.quest_condition_set)。"""
    cg_id = quest_cfg.get("condition_set_group_i_d")
    out = []
    for cg in res["Quest"]["condition_set_group"]["datas"]:
        if isinstance(cg, dict) and cg.get("i_d") == cg_id:
            for e in cg.get("quest_condition_set", ()) or ():
                aid = e.get("achieve_condition_i_d")
                if isinstance(aid, (list, tuple)):
                    out.extend(x for x in aid if x)
                elif aid:
                    out.append(aid)
            break
    return out


_extra_gate = None


def _extra_gate_cfg(quest_id):
    """extra_chapter 支线开启条件: {quest_i_d: extra_quest条目}(懒加载)。"""
    global _extra_gate
    if _extra_gate is None:
        gate = {}
        for c in res["Story"]["extra_chapter"]["datas"]:
            for e in c.get("extra_quest", ()) or ():
                if e.get("quest_i_d"):
                    gate[e["quest_i_d"]] = e
        _extra_gate = gate
    return _extra_gate.get(quest_id)


"""
# 领取任务/剧情奖励 1725 1726
两条链路(均已对表验证):
1. 剧情: req.quest_id 是 Story.story 的 i_d(出现在 Story.story_chapter.story_list 中),
   奖励为 Story.story.reward(Reward.reward_pool 入口, 如 story 1000001 -> 2010101
   -> 经验x300/星石x50/金币x300 等); 领取状态持久化在 Chapter.rewarded_story_ids。
2. 普通任务: req.quest_id 是 Quest.quest 的 i_d, 奖励为 Quest.quest.reward,
   首次完成另发 Quest.quest.first_reward(如 quest 301011: reward=2000310,
   first_reward=2301011); 领取次数记在 Quest blob 的 complete_count,
   超过 Quest.quest.limit_num 判重复。
"""


@packet_handler(MsgId.ClaimQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        try:
            self._handle(session, data, packet_id)
        except item_mgr.EconomyConfigError:
            session.send(
                MsgId.ClaimQuestRewardRsp,
                ClaimQuestRewardRsp(status=StatusCode.StatusCode_CFG_NOT_FOUND),
                packet_id,
            )

    def _handle(self, session, data: bytes, packet_id: int):
        req = ClaimQuestRewardReq()
        req.ParseFromString(data)

        rsp = ClaimQuestRewardRsp()
        level = _player_level(session.player_id)

        # ---- 链路1: 剧情奖励(Story.story_chapter.story_list 含 quest_id) ----
        chapter_cfg = None
        for chapter in res["Story"]["story_chapter"]["datas"]:
            if req.quest_id in chapter.get("story_list", ()):
                chapter_cfg = chapter
                break

        if chapter_cfg is None:
            # 章节外剧情(如 1000401~1000414/1000509/1000510 分支节点):
            # 属于 Story.story 的合法主线, 用 chapter_id=0 桶持久化领取状态,
            if any(
                s.get("i_d") == req.quest_id for s in res["Story"]["story"]["datas"]
            ):
                chapter_cfg = {"i_d": 0}

        if chapter_cfg:
            story_cfg = next(
                (s for s in res["Story"]["story"]["datas"] if s["i_d"] == req.quest_id),
                None,
            )
            if story_cfg is None:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
                return
            quest_i_d = story_cfg.get("quest_i_d")
            notice = PackNotice(status=StatusCode.StatusCode_OK)
            try:
                with item_mgr.player_lock(session.player_id), db.transaction():
                    tmp = Chapter(chapter_id=chapter_cfg["i_d"])
                    for blob in db.get_chapter(session.player_id):
                        chapter = Chapter.FromString(blob)
                        if chapter.chapter_id == chapter_cfg["i_d"]:
                            tmp.CopyFrom(chapter)
                            break
                    if req.quest_id in tmp.rewarded_story_ids:
                        rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                    else:
                        pre_story = story_cfg.get("pre_story_unlock")
                        if pre_story and not db.is_story_rewarded(session.player_id, pre_story):
                            rsp.status = StatusCode.StatusCode_BAD_REQ
                        elif not quest_i_d or not _qt.is_completed_live(session.player_id, quest_i_d):
                            rsp.status = StatusCode.StatusCode_BAD_REQ
                        else:
                            reward_list = _required_rewards(story_cfg.get("reward"), level)
                            if quest_i_d:
                                rsp.quest.CopyFrom(
                                    _chain_tail_echo(session.player_id, quest_i_d)
                                )
                            item_mgr.grant_items(
                                session.player_id,
                                reward_list,
                                rsp_items=rsp.items,
                                pack_notice=notice,
                                session=session,
                            )
                            tmp.rewarded_story_ids.append(req.quest_id)
                            db.set_chapter(
                                session.player_id,
                                tmp.chapter_id,
                                tmp.SerializeToString(),
                            )
                            rsp.status = StatusCode.StatusCode_OK
            except item_mgr.EconomyConfigError:
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                del rsp.items[:]
                del notice.items[:]
            with achieve_track.batch(session):
                session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
                if rsp.status == StatusCode.StatusCode_OK and notice.items:
                    session.send(MsgId.PackNotice, notice, 0)
            return

        # ---- 链路2: 普通任务奖励(Quest.quest.reward / first_reward) ----
        quest_cfg = None
        for q in res["Quest"]["quest"]["datas"]:
            if q["i_d"] == req.quest_id:
                quest_cfg = q
                break

        if not quest_cfg:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
            return

        quest = Quest()
        quest_b = db.get_quest(session.player_id, req.quest_id)
        if not quest_b:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
            return
        quest.ParseFromString(quest_b)
        if quest.status not in Config.QUEST_TRACK_DONE and not _qt.is_completed_live(session.player_id, req.quest_id):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            rsp.quest.CopyFrom(quest)
            session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
            return

        gate = _extra_gate_cfg(req.quest_id)
        if gate:
            if level < int(gate.get("lv_unlock") or 1):
                rsp.status = StatusCode.StatusCode_FAIL
                rsp.quest.CopyFrom(quest)
                session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
                return
            unlock_q = gate.get("quest_unlock")
            if unlock_q and not db.is_quest_completed(session.player_id, unlock_q):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                rsp.quest.CopyFrom(quest)
                session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
                return

        limit = quest_cfg.get("limit_num", 0)
        if limit and quest.complete_count >= limit:
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            rsp.quest.CopyFrom(quest)
            session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
            return

        notice = PackNotice(status=StatusCode.StatusCode_OK)
        limit_reached = False
        invalid = False
        with item_mgr.player_lock(session.player_id), db.transaction():
            latest_blob = db.get_quest(session.player_id, req.quest_id)
            latest = Quest()
            latest.ParseFromString(latest_blob)
            if limit and latest.complete_count >= limit:
                limit_reached = True
            else:
                if latest.status not in Config.QUEST_TRACK_DONE and not _qt.is_completed_live(session.player_id, req.quest_id):
                    invalid = True
                else:
                    reward_list = _required_rewards(quest_cfg.get("reward"), level)
                    if latest.complete_count == 0:
                        reward_list += _required_rewards(quest_cfg.get("first_reward"), level)
                    latest.complete_count += 1
                    latest.status = QuestStatus.QuestStatus_Finish
                    latest.bonus_times = max(latest.bonus_times, 1)
                    db.set_quest(session.player_id, req.quest_id, latest.SerializeToString())
                    item_mgr.grant_items(
                        session.player_id,
                        reward_list,
                        rsp_items=rsp.items,
                        pack_notice=notice,
                        session=session,
                    )
                    quest.CopyFrom(latest)
        if invalid:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
            return
        if limit_reached:
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            rsp.quest.CopyFrom(quest)
            session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
            return
        session.quests[req.quest_id] = quest
        rsp.status = StatusCode.StatusCode_OK
        rsp.quest.CopyFrom(quest)
        session.send(MsgId.ClaimQuestRewardRsp, rsp, packet_id)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
