"""活动实例、奖励模板和登录状态的统一解析。"""

from datetime import datetime
import time

from config import Config
from proto import net_pb2 as pb
from network.msg_id import MsgId
import utils.db as db
from utils import achieve_track, refresh
from utils.res_loader import res

_PERIOD_SPECS = None


def period_specs():
    """周期任务只保存通用计数的基线，不另存行为次数。"""
    global _PERIOD_SPECS
    if _PERIOD_SPECS is None:
        specs = {}
        for aid, kind, template, _, _ in active_instances():
            if kind == 3:
                row = next(
                    (
                        r
                        for r in res["BattlePass"]["battle_pass"]["datas"]
                        if r["i_d"] == template
                    ),
                    {},
                )
                for key, period in (("day_quest_i_d", "d"), ("week_quest_i_d", "w")):
                    group = next(
                        (
                            g
                            for g in res["BattlePass"]["battle_pass_queset"]["datas"]
                            if g["i_d"] == row.get(key)
                        ),
                        {},
                    )
                    for item in group.get("battle_pass_queset_item", ()):
                        specs[item["achieve_i_d"]] = (aid, period)
            elif kind == 4:
                row = next(
                    (
                        r
                        for r in res["ActivityRegular"]["activity_regular"]["datas"]
                        if r["i_d"] == template
                    ),
                    {},
                )
                pools = {row.get("daily_pool_i_d"), row.get("daily_refresh_pool_i_d")}
                for pool in res["ActivityRegular"]["activity_regular_pool"]["datas"]:
                    if pool["i_d"] in pools:
                        for item in pool.get("activity_regular_pool_item", ()):
                            specs[item["achieve_i_d"]] = (aid, "d")
        _PERIOD_SPECS = specs
    return _PERIOD_SPECS


def period_token(condition_id):
    spec = period_specs().get(condition_id)
    if spec is None:
        return ""
    return (
        f"d{refresh.day_index()}" if spec[1] == "d" else "w" + time.strftime("%G-W%V")
    )


def prepare_counter_period(player_id, condition_id, current):
    token = period_token(condition_id)
    if not token:
        return
    key = f"{condition_id}:{token}"
    if db.get_kv(player_id, "activity_counter_base", key) is None:
        db.set_kv(player_id, "activity_counter_base", key, current)


def condition_progress(player_id, condition_id):
    count = achieve_track.progress(player_id, condition_id)
    token = period_token(condition_id)
    if not token:
        return count
    prepare_counter_period(player_id, condition_id, count)
    baseline = db.get_kv(
        player_id, "activity_counter_base", f"{condition_id}:{token}", 0
    )
    return max(0, count - int(baseline))


def bp_claim_key(activity_id, condition_id):
    token = period_token(condition_id)
    return f"{activity_id}:{condition_id}" + (f":{token}" if token else "")


def template_id(activity_id):
    override = Config.ACTIVITY_INSTANCES.get(activity_id)
    if override:
        return override[1]
    row = next(
        (
            r
            for r in res["Activity"]["activity"]["datas"]
            if r.get("i_d") == activity_id
        ),
        None,
    )
    return row.get("activity_i_d", activity_id) if row else activity_id


def active_instances():
    now = int(time.time() * 1000)
    replaced = {
        (kind, template) for kind, template, _, _ in Config.ACTIVITY_INSTANCES.values()
    }
    entries = {
        aid: entry
        for aid, entry in Config.ACTIVITY_INSTANCES.items()
        if aid in Config.ACTIVITY_VISIBLE_IDS
    }
    for row in res["Activity"]["activity"]["datas"]:
        aid = row["i_d"]
        kind = row.get("new_activity_type", 0)
        template = row.get("activity_i_d", aid)
        if (
            aid not in Config.ACTIVITY_VISIBLE_IDS
            or aid in entries
            or aid in Config.INACTIVE_ACTIVITY_IDS
            or (kind, template) in replaced
        ):
            continue
        opening = row.get("opening_time")
        closing = row.get("closing_time")
        start = (
            int(datetime.strptime(opening, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
            if opening
            else 0
        )
        end = (
            int(datetime.strptime(closing, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
            if closing
            else 0
        )
        entries[aid] = (kind, template, start, end)
    return [
        (aid, *entries[aid])
        for aid in Config.ACTIVITY_VISIBLE_IDS
        if aid in entries
        for kind, template, start, end in (entries[aid],)
        if start <= now and (not end or now <= end)
    ]


def tracker_specs(player_id):
    """从生活等级、通用能力族和当前活动实际配置构造条件集合。"""
    entries = {}
    for life_type, (
        sheet,
        level_sheet,
        quest_key,
    ) in Config.LIFE_ACHIEVE_LIFE_TABLES.items():
        blob = db.get_life(player_id, life_type)
        info = pb.LifeBaseInfo()
        if blob:
            info.ParseFromString(blob)
        row = next(
            (
                r
                for r in res[sheet][level_sheet]["datas"]
                if r["i_d"] == max(1, info.level)
            ),
            {},
        )
        for item in row.get(quest_key, ()):
            entries[item["achieve_condition_i_d"]] = (0, item.get("complete_limit", 0))
    for row in res["Achieve"]["achieve"]["datas"]:
        if (
            row.get("new_function_of_achievement") == 32
            and row.get("i_d")
            and row["i_d"] not in Config.HIDDEN_EVENT_TRACKERS
        ):
            entries[row["i_d"]] = (0, 0)
    for aid, kind, template, _, _ in active_instances():
        if kind == 0:
            row = next(
                (
                    r
                    for r in res["ActivityQuest"]["activity_quest"]["datas"]
                    if r["i_d"] == template
                ),
                {},
            )
            for item in row.get("activity_quest_achieve_items", ()):
                entries[item["achieve_i_d"]] = (aid, 0)
        elif kind == 3:
            row = next(
                (
                    r
                    for r in res["BattlePass"]["battle_pass"]["datas"]
                    if r["i_d"] == template
                ),
                {},
            )
            groups = {
                row.get(key)
                for key in ("day_quest_i_d", "week_quest_i_d", "season_quest_i_d")
            }
            for group in res["BattlePass"]["battle_pass_queset"]["datas"]:
                if group["i_d"] in groups:
                    for item in group.get("battle_pass_queset_item", ()):
                        entries[item["achieve_i_d"]] = (aid, 0)
        elif kind == 4:
            row = next(
                (
                    r
                    for r in res["ActivityRegular"]["activity_regular"]["datas"]
                    if r["i_d"] == template
                ),
                {},
            )
            pools = {
                row.get(key)
                for key in (
                    "daily_pool_i_d",
                    "pool_i_d",
                    "daily_refresh_pool_i_d",
                    "random_pool_i_d",
                )
            }
            for pool in res["ActivityRegular"]["activity_regular_pool"]["datas"]:
                if pool["i_d"] in pools:
                    for item in pool.get("activity_regular_pool_item", ()):
                        entries[item["achieve_i_d"]] = (aid, 0)
    return entries


def quest_trackers(player_id, condition_ids=None):
    entries = tracker_specs(player_id)
    selected = entries if condition_ids is None else condition_ids
    result = []
    for condition_id in selected:
        if condition_id not in entries:
            continue
        activity_id, limit = entries[condition_id]
        count = condition_progress(player_id, condition_id)
        target = achieve_track.target_of(condition_id) or 1
        quest = pb.Quest(
            status=pb.QuestStatus_InProgress, bonus_times=1, activity_id=activity_id
        )
        condition = quest.conditions.add(
            condition_id=condition_id, status=pb.QuestStatus_InProgress
        )
        if condition_id // 10000 == 2001:
            # 事件tracker只提示该行为发生；永久累计值不映射成完成状态。
            pass
        elif limit:
            key = f"{refresh.day_index()}:{condition_id}"
            baseline = db.get_kv(player_id, "life_proficiency_base", key)
            if baseline is None:
                baseline = count
                db.set_kv(player_id, "life_proficiency_base", key, baseline)
            complete, remainder = divmod(max(0, count - int(baseline)), target)
            quest.complete_count = min(complete, limit)
            condition.progress = remainder if complete < limit else 0
        else:
            condition.progress = min(count, target)
            if count >= target:
                condition.status = pb.QuestStatus_Completed
                quest.status = pb.QuestStatus_Completed
        result.append(quest)
    return result


def send_login_notices(session):
    pid = session.player_id
    notices = {
        0: pb.ActivityQuestDataNotice(status=pb.StatusCode_OK),
        1: pb.ActivitySignInDataNotice(status=pb.StatusCode_OK),
        2: pb.ActivityGiftDataNotice(status=pb.StatusCode_OK),
        3: pb.ActivityBattlePassInfoNotice(status=pb.StatusCode_OK),
        4: pb.ActivityRegularDataNotice(status=pb.StatusCode_OK),
        6: pb.ActivityTurntableDataNotice(status=pb.StatusCode_OK),
    }
    now = int(time.time())
    day = str(refresh.day_index())
    for aid, kind, template, start, end in active_instances():
        notice = notices.get(kind)
        if notice is None:
            continue
        info = notice.activities.add() if kind == 6 else notice.info.add()
        info.activity_id, info.open_time, info.close_time = aid, start, end
        if kind == 1:
            if db.get_kv(pid, "sign_in", f"{aid}:last") != day:
                db.incr_kv(pid, "sign_in", f"{aid}:days")
                db.set_kv(pid, "sign_in", f"{aid}:last", day)
            info.login_day = int(db.get_kv(pid, "sign_in", f"{aid}:days", 0))
            initialized = db.get_kv(pid, "sign_in", f"{aid}:init", 0)
            if not initialized:
                initialized = db.get_players_info(pid, "create_time")[0]
                db.set_kv(pid, "sign_in", f"{aid}:init", initialized)
            info.init_time = int(initialized)
            info.reward_id = sum(
                1 << int(key.split(":")[1])
                for key in db.get_claimed(pid, "activity_sign")
                if key.startswith(f"{aid}:")
            )
        elif kind == 0:
            info.open_day = max(1, (now - start // 1000) // 86400 + 1) if start else 1
            for key in db.get_claimed(pid, "activity_quest"):
                parts = key.split(":")
                if len(parts) == 3 and parts[0] == str(aid):
                    target = (
                        info.progress_reward
                        if parts[1] == "progress"
                        else info.reward_achieve
                    )
                    target.append(int(parts[2]))
        elif kind == 4:
            row = next(
                (
                    r
                    for r in res["ActivityRegular"]["activity_regular"]["datas"]
                    if r["i_d"] == template
                ),
                {},
            )
            for pool_type, field, key in (
                (1, "daily_achieve", "daily_pool_i_d"),
                (3, "pool_achieve", "pool_i_d"),
                (1, "daily_refresh_achieve", "daily_refresh_pool_i_d"),
                (2, "pool_achieve", "random_pool_i_d"),
            ):
                pool = next(
                    (
                        r
                        for r in res["ActivityRegular"]["activity_regular_pool"][
                            "datas"
                        ]
                        if r["i_d"] == row.get(key)
                    ),
                    {},
                )
                pool_items = pool.get("activity_regular_pool_item", ())
                for item in pool_items:
                    condition = item["achieve_i_d"]
                    claim_key = f"{aid}:{pool_type}:{condition}"
                    if pool_type == 1:
                        claim_key += f":d{day}"
                    getattr(info, field).add(
                        achieve_id=condition,
                        is_reward=db.has_claimed(pid, "activity_regular", claim_key),
                    )
        elif kind == 3:
            info.level, info.total_exp, info.current_exp = db.bp_get_exp(pid, aid)
            info.week_exp = int(
                db.get_kv(pid, "battle_pass_week", "exp:" + time.strftime("%G-W%V"), 0)
            )
            row = next(
                (
                    r
                    for r in res["BattlePass"]["battle_pass"]["datas"]
                    if r["i_d"] == template
                ),
                {},
            )
            for field, key in (
                ("daily_achieve_reward_lst", "day_quest_i_d"),
                ("weekly_achieve_reward_lst", "week_quest_i_d"),
                ("season_achieve_reward_lst", "season_quest_i_d"),
            ):
                group = next(
                    (
                        r
                        for r in res["BattlePass"]["battle_pass_queset"]["datas"]
                        if r["i_d"] == row.get(key)
                    ),
                    {},
                )
                for quest in group.get("battle_pass_queset_item", ()):
                    condition = quest["achieve_i_d"]
                    if db.has_claimed(
                        pid, "bp_quest_reward", bp_claim_key(aid, condition)
                    ):
                        getattr(info, field).append(condition)
        elif kind == 2:
            info.rewarded_id_lst.extend(
                int(key.split(":")[1])
                for key in db.get_claimed(pid, "activity_gift")
                if key.startswith(f"{aid}:")
            )
        elif kind == 6:
            row = next(
                (
                    r
                    for r in res["ActivityTurntable"]["activity_turntable"]["datas"]
                    if r["i_d"] == template
                ),
                {},
            )
            pool = next(
                (
                    r
                    for r in res["ActivityTurntable"]["turntable_pool"]["datas"]
                    if r["i_d"] == row.get("turntable_pool_i_d")
                ),
                {},
            )
            used = db.get_turntable_used_counts(pid, aid)
            for item in pool.get("turntable_pool_item", ()):
                slot = info.items[item["index"]]
                slot.index, slot.item_id, slot.item_num = (
                    item["index"],
                    item["item_i_d"],
                    item["item_num"],
                )
                slot.remain_count = max(
                    0, item.get("limit_num", 0) - used.get(slot.index, 0)
                )
                slot.is_special = item.get("is_special", False)
            info.single_discount = not db.has_turntable_drawn(pid, aid)
    # 官服登录序列；未参与的玩法仍发送空状态通知。
    for kind in (4, 3, 2):
        notice = notices[kind]
        session.send(getattr(MsgId, type(notice).__name__), notice, 0)
    session.send(
        MsgId.ActivityRecallNotice, pb.ActivityRecallNotice(status=pb.StatusCode_OK), 0
    )
    for kind in (1, 0):
        notice = notices[kind]
        session.send(getattr(MsgId, type(notice).__name__), notice, 0)
    session.send(
        MsgId.ActivitySandbagNotice,
        pb.ActivitySandbagNotice(status=pb.StatusCode_OK),
        0,
    )
    session.send(
        MsgId.ActivityKoiNotice, pb.ActivityKoiNotice(status=pb.StatusCode_OK), 0
    )
    session.send(MsgId.ActivityTurntableDataNotice, notices[6], 0)
