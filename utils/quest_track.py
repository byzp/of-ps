"""按成就计数镜像并推进任务，领取判定实时读取成就。"""

from config import Config
import random
import utils.db as db

from network.msg_id import MsgId
from proto.net_pb2 import (
    Achieve,
    DailyTaskUpdateNotice,
    PackNotice,
    Quest,
    QuestNotice,
    QuestStatus,
    StatusCode,
)
from utils import achieve_track, flag_state, item_mgr, refresh, activity_state
from utils.pb_create import make_Quest
from utils.res_loader import res
from utils.reward_resolver import resolve_reward

# achieve_condition_i_d -> [(quest_id, need), ...]
_COND_QUESTS = None
_DAILY_CONDITIONS = None


def event_condition_active(player_id, achieve_id):
    """日常条件仅在当天任务已接受时计数，其他通用成就保持历史累计。"""
    global _DAILY_CONDITIONS
    if _DAILY_CONDITIONS is None:
        daily_ids = {
            row["i_d"]
            for row in res["Quest"]["quest"]["datas"]
            if row.get("new_type") == 7
        }
        _DAILY_CONDITIONS = {
            aid: tuple(qid for qid, _ in entries if qid in daily_ids)
            for aid, entries in _cond_quests().items()
            if any(qid in daily_ids for qid, _ in entries)
        }
    qids = _DAILY_CONDITIONS.get(achieve_id)
    if not qids:
        return True
    for qid in qids:
        blob = db.get_quest(player_id, qid)
        if blob:
            quest = Quest()
            quest.ParseFromString(blob)
            if quest.status == QuestStatus.QuestStatus_InProgress:
                return True
    return False


def _build():
    global _COND_QUESTS
    ach = {
        r["i_d"]: r
        for r in res["Achieve"]["achieve"]["datas"]
        if isinstance(r, dict) and "i_d" in r
    }
    _COND_QUESTS = {}
    groups = {
        g["i_d"]: g
        for g in res["Quest"]["condition_set_group"]["datas"]
        if isinstance(g, dict) and "i_d" in g
    }
    for quest in res["Quest"]["quest"]["datas"]:
        qid = quest["i_d"]
        g = groups.get(quest.get("condition_set_group_i_d"))
        if not g:
            continue
        for cs in g.get("quest_condition_set") or ():
            for cid in cs.get("achieve_condition_i_d") or ():
                c = ach.get(cid)
                if not c:
                    continue
                need = int(c.get("count_param") or 1)
                _COND_QUESTS.setdefault(cid, []).append((qid, need))
    return _COND_QUESTS


def _cond_quests():
    if _COND_QUESTS is None:
        _build()
    return _COND_QUESTS


def _achieve_count(player_id, aid):
    """成就条件当前计数(无记录按 0)"""
    return achieve_track.progress(player_id, aid)


def advance(session, achieve_id):
    """单个条件与批量条件共用推进和tracker通知路径。"""
    advance_many(session, [achieve_id])


def advance_many(session, achieve_ids, send=True):
    """多个成就条件的链推进合并为一份 QuestNotice(一个动作一条消息)。"""
    notice = QuestNotice()
    notice.status = StatusCode.StatusCode_OK
    if db.has_unlock_function(session.player_id, Config.DAILY_TASK_UNLOCK_FUNCTION_ID):
        notice.random_quest_bonus_info.SetInParent()
    pack_notice = PackNotice()
    pack_notice.status = StatusCode.StatusCode_OK
    touched = False
    seen = set()
    for aid in achieve_ids:
        if aid in seen:
            continue
        seen.add(aid)
        if _advance_into(session, aid, notice, pack_notice):
            touched = True
    trackers = activity_state.quest_trackers(session.player_id, achieve_ids)
    notice.quests.extend(trackers)
    if touched or trackers:
        if not send:
            return notice, pack_notice
        if pack_notice.items:
            session.send(MsgId.PackNotice, pack_notice, 0)
        session.send(MsgId.QuestNotice, notice, 0)
    return None


def _advance_into(session, achieve_id, notice, pack_notice):
    """推进实现(不发送): 时序语义:
    - 只推进"已接受(blob 存在)且未完成"的任务 —— 接取时第一个子任务
      InProgress, 后续子任务由前置完成置 Finish 后自动创建进入进行中;
    - 条件达标(计数>=count_param)置 Finish, 任务须全部条件 Finish 才完成
      (多条件任务); 一个条件被多个任务共享时, 全部引用任务一并推进;
    - 任务 Finish 时移出 session.quests, 按 Quest.quest 相邻同名链自动
      创建下一任务(同名断即链尽)。返回是否有变更。"""
    entries = _cond_quests().get(achieve_id)
    if not entries:
        return False
    quests = getattr(session, "quests", None)
    if quests is None:
        quests = session.quests = {}
    pid = session.player_id
    cur = achieve_track.progress(pid, achieve_id)
    quest_rows = res["Quest"]["quest"]["datas"]
    level_row = db.get_players_info(pid, "level")
    level = level_row[0] if level_row else 0
    touched = False
    for qid, need in entries:
        blob = db.get_quest(pid, qid)
        if not blob:
            continue  # 未接受的任务不推进(时序: 上一环 Finish 后才会建下一环)
        q = Quest()
        q.ParseFromString(blob)
        if q.status in Config.QUEST_TRACK_DONE:
            continue  # 已完成(待领取/已领取), 不重复推进
        hit = False
        for c in q.conditions:
            if c.condition_id == achieve_id:
                progress = min(cur, need)
                status = (
                    QuestStatus.QuestStatus_Completed
                    if cur >= need
                    else QuestStatus.QuestStatus_InProgress
                )
                if c.progress != progress or c.status != status:
                    c.status = status
                    c.progress = progress
                    hit = True
        quest_cfg = next(
            (row for row in quest_rows if row.get("i_d") == qid),
            None,
        )
        group_cfg = next(
            (
                row
                for row in res["Quest"]["condition_set_group"]["datas"]
                if row.get("i_d") == (quest_cfg or {}).get("condition_set_group_i_d")
            ),
            None,
        )
        condition_sets = group_cfg.get("quest_condition_set") or () if group_cfg else ()
        all_done = False
        if condition_sets:
            for condition_set in condition_sets:
                condition_ids = condition_set.get("achieve_condition_i_d") or ()
                if condition_ids and all(
                    any(
                        condition.condition_id == condition_id
                        and condition.status in Config.QUEST_TRACK_DONE
                        for condition in q.conditions
                    )
                    for condition_id in condition_ids
                ):
                    all_done = True
                    break
        else:
            all_done = all(c.status in Config.QUEST_TRACK_DONE for c in q.conditions)
        if not hit and not (all_done and q.status not in Config.QUEST_TRACK_DONE):
            continue
        if all_done:
            immediate = bool(quest_cfg and quest_cfg.get("is_immed_reward"))
            q.status = (
                QuestStatus.QuestStatus_Finish
                if immediate
                else QuestStatus.QuestStatus_Completed
            )
            for condition in q.conditions:
                condition.status = QuestStatus.QuestStatus_Finish
            flag_state.finish_quest(session, q)
            if quest_cfg and quest_cfg.get("is_immed_reward"):
                # 即时任务没有后续 ClaimQuestReward 请求。complete_count
                # 既是客户端展示状态，也是防止重复计奖的持久化幂等位。
                if q.complete_count == 0:
                    reward_list = resolve_reward(quest_cfg.get("reward"), level)
                    reward_list += list(
                        Config.QUEST_COMPLETION_EXTRA_ITEMS.get(qid, ())
                    )
                    item_mgr.grant_items(
                        pid,
                        reward_list,
                        pack_notice=pack_notice,
                        session=session,
                    )
                    q.complete_count = 1
        db.set_quest(pid, qid, q.SerializeToString())
        echoed = next((e for e in notice.quests if e.quest_id == qid), None)
        if echoed is None:
            echoed = notice.quests.add()
        echoed.CopyFrom(q)
        touched = True
        if all_done:
            quests.pop(qid, None)
            pos = next(
                (i for i, e in enumerate(quest_rows) if e.get("i_d") == qid),
                None,
            )
            if (
                pos is not None
                and pos + 1 < len(quest_rows)
                and quest_rows[pos].get("quest_group")
                and quest_rows[pos + 1].get("quest_group")
                == quest_rows[pos].get("quest_group")
            ):
                nq = notice.quests.add()
                make_Quest(pid, quest_rows[pos + 1]["i_d"], nq)
                db.set_quest(pid, nq.quest_id, nq.SerializeToString())
                quests[nq.quest_id] = nq
                flag_state.unlock_for_quest(session, nq)
            # 类型136按任务真正进入 Finish 计数，而不是按客户端是否随后领取奖励计数。
            achieve_track.report(session, "quest_complete", match=qid)
            if qid == Config.DAILY_TASK_UNLOCK_QUEST_ID:
                start_daily_tasks(session, notice)
            for new_id in Config.QUEST_COMPLETION_START_QUESTS.get(qid, ()):
                if db.get_quest(pid, new_id):
                    continue
                new_quest = make_Quest(pid, new_id, notice.quests.add())
                db.set_quest(pid, new_id, new_quest.SerializeToString())
                quests[new_id] = new_quest
                flag_state.unlock_for_quest(session, new_quest)
    return touched


def start_daily_tasks(session, notice=None):
    """恢复当天祈愿任务；初次解锁或跨日时选取任务并保存。"""
    if not db.has_unlock_function(
        session.player_id, Config.DAILY_TASK_UNLOCK_FUNCTION_ID
    ):
        return {}
    day = str(refresh.day_index())
    raw = db.get_kv(session.player_id, "daily_task", day, b"")
    created = not raw
    if raw:
        picks = [int(value) for value in raw.decode().split(",") if value]
    else:
        pool = [
            row["i_d"]
            for row in res["Quest"]["quest"]["datas"]
            if row.get("new_type") == 7
        ]
        rng = random.Random(f"{session.player_id}:{day}")
        picks = sorted(rng.sample(pool, min(4, len(pool))))
        # 日常任务跨日重置，只重置这些任务专用的条件，不清通用历史成就。
        for qid in pool:
            db.delete_quest(session.player_id, qid)
            session.quests.pop(qid, None)
        db.set_kv(
            session.player_id, "daily_task", day, ",".join(map(str, picks)).encode()
        )
    tasks = dict(enumerate(picks, start=1))
    for qid in picks:
        blob = db.get_quest(session.player_id, qid)
        if created or not blob:
            quest = make_Quest(session.player_id, qid)
            if created:
                for condition in quest.conditions:
                    achieve = Achieve(achieve_id=condition.condition_id)
                    db.set_achieve(
                        session.player_id,
                        condition.condition_id,
                        achieve.SerializeToString(),
                    )
                    db.del_kv(session.player_id, "ach", f"f:{condition.condition_id}")
                    condition.progress = 0
            db.set_quest(session.player_id, qid, quest.SerializeToString())
            session.quests[qid] = quest
            if notice is not None:
                notice.quests.add().CopyFrom(quest)
    if created and notice is not None:
        update = DailyTaskUpdateNotice()
        update.status = StatusCode.StatusCode_OK
        update.tasks.update(tasks)
        session.send(MsgId.DailyTaskUpdateNotice, update, 0)
        notice.random_quest_bonus_info.SetInParent()
    return tasks


def is_completed_live(player_id, story_quest_i_d):
    """任务是否已完成。

    剧情绑定的是 quest_group 的首个子任务, 因此必须检查该组连续子任务;
    每个子任务内 quest_condition_set 为可选分支(分支内条件需全部满足)。
    """
    quest_rows = res["Quest"]["quest"]["datas"]
    start = next(
        (i for i, row in enumerate(quest_rows) if row.get("i_d") == story_quest_i_d),
        None,
    )
    if start is None:
        return False

    head = quest_rows[start]
    group_id = head.get("quest_group")
    chain = [head]
    if group_id:
        for row in quest_rows[start + 1 :]:
            if row.get("quest_group") != group_id:
                break
            chain.append(row)

    ach = {}
    for r in res["Achieve"]["achieve"]["datas"]:
        if isinstance(r, dict) and "i_d" in r:
            ach[r["i_d"]] = r
    condition_groups = {
        row["i_d"]: row
        for row in res["Quest"]["condition_set_group"]["datas"]
        if isinstance(row, dict) and "i_d" in row
    }

    for quest_cfg in chain:
        blob = db.get_quest(player_id, quest_cfg["i_d"])
        if blob:
            q = Quest()
            q.ParseFromString(blob)
            if q.status in (
                QuestStatus.QuestStatus_Completed,
                QuestStatus.QuestStatus_Finish,
            ):
                continue

        group = condition_groups.get(quest_cfg.get("condition_set_group_i_d"))
        condition_sets = group.get("quest_condition_set") or () if group else ()
        if not condition_sets:
            return False
        quest_done = False
        for condition_set in condition_sets:
            condition_ids = condition_set.get("achieve_condition_i_d") or ()
            if condition_ids and all(
                cid in ach
                and _achieve_count(player_id, cid)
                >= int(ach[cid].get("count_param") or 1)
                for cid in condition_ids
            ):
                quest_done = True
                break
        if not quest_done:
            return False
    return True
