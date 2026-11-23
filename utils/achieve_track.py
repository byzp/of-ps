"""按事件统一推进成就与任务计数。

handler 只上报事件名，条件类型与计数规则由本模块和 Config 决定。
"""

from config import Config
import json
import logging
import threading
import time

import utils.db as db
from network.msg_id import MsgId
from proto.net_pb2 import (
    Achieve as PbAchieve,
    AchieveFinishNotice,
    AchieveNotice,
    Character as PbChar,
    FinishAchieveInfo,
    StatusCode,
)
from utils import quest_track as _quest_track
from utils import activity_state
from utils.refresh import day_index
from utils.res_loader import res

log = logging.getLogger("achieve_track")

_INDEX = None  # {cond_type: [(i_d, param_tuple, count_param)]}
_TRACKER_IDS = None
_FINISH_NOTICE_IDS = None


def tracker_ids():
    global _TRACKER_IDS
    if _TRACKER_IDS is None:
        _TRACKER_IDS = {
            row["i_d"]
            for row in res["Achieve"]["achieve"]["datas"]
            if row.get("i_d")
            and row.get("new_function_of_achievement")
            in Config.ACHIEVE_TRACKER_FUNCTIONS
        }
    return _TRACKER_IDS


def finish_notice_ids():
    global _FINISH_NOTICE_IDS
    if _FINISH_NOTICE_IDS is None:
        _FINISH_NOTICE_IDS = {
            item["achieve_condition_i_d"]
            for group in res["AchieveQuest"]["achieve_quest_group"]["datas"]
            for item in group.get("achieve_quest_group_info", ())
        }
    return _FINISH_NOTICE_IDS


def _index():
    global _INDEX
    if _INDEX is None:
        idx = {}
        for row in res.get("Achieve", {}).get("achieve", {}).get("datas", []):
            if not isinstance(row, dict) or "i_d" not in row:
                continue
            t = row.get("new_achieve_condition")
            if t is None:
                continue
            idx.setdefault(t, []).append(
                (
                    row["i_d"],
                    tuple(row.get("param") or ()),
                    int(row.get("count_param") or 1),
                )
            )
        _INDEX = idx
    return _INDEX


def progress(player_id, achieve_id):
    """当前计数(无记录为 0)"""

    blob = db.get_achieve(player_id, achieve_id)
    if not blob:
        return 0
    a = PbAchieve()
    a.ParseFromString(blob)
    return int(a.count)


def is_finished(player_id, achieve_id):

    return bool(db.get_kv(player_id, "ach", f"f:{achieve_id}"))


def _world_of(session):
    """玩家当前世界 id(1~8); 取不到返回 None"""
    wid = getattr(session, "scene_id", 0) or 0
    return wid if 0 < wid < 100 else (wid // 1000 or None)


# 动作级通知缓冲: 一次动作(开箱/拾取/登录…)内部所有成就计数合并为
_ACC = threading.local()


def _acc():
    return getattr(_ACC, "cur", None)


def _notice_progress(session, achieve_id, count):
    if achieve_id in tracker_ids():
        return
    acc = _acc()
    if acc is not None:
        if achieve_id not in acc["prog"]:
            acc["order"].append(achieve_id)
        acc["prog"][achieve_id] = count
        return

    n = AchieveNotice()
    n.status = StatusCode.StatusCode_OK
    a = n.achieves.add()
    a.achieve_id = achieve_id
    a.count = count
    session.send(MsgId.AchieveNotice, n, 0)  # 1720


def _advance_quest(session, achieve_id):
    """任务推进统一入口(时序由 quest_track.advance 保证)。"""

    _quest_track.advance(session, achieve_id)


def _write(session, player_id, achieve_id, count):
    if not _quest_track.event_condition_active(player_id, achieve_id):
        return
    if count == progress(player_id, achieve_id):
        return
    activity_state.prepare_counter_period(
        player_id, achieve_id, progress(player_id, achieve_id)
    )
    a = PbAchieve()
    a.achieve_id = achieve_id
    a.count = count
    db.set_achieve(player_id, achieve_id, a.SerializeToString())
    _notice_progress(session, achieve_id, count)
    # 任务依赖推进: 成就计数为事实源, 镜像到引用该条件的任务;
    # 缓冲内延后到 flush
    acc = _acc()
    if acc is None:
        _advance_quest(session, achieve_id)
    elif achieve_id not in acc["quest"]:
        acc["quest"].append(achieve_id)


def batch(session, notify=True):
    """动作通知缓冲上下文: with batch(session): 帧内全部计数合并为
    一份 AchieveNotice, 随后逐个 1764 与一份 QuestNotice(advance_many)。
    可嵌套, 最外层退出时发送。"""

    class _B:
        def __enter__(self):
            depth = getattr(_ACC, "depth", 0)
            if depth == 0:
                _ACC.cur = {
                    "prog": {},
                    "order": [],
                    "quest": [],
                    "finished": [],
                    "prepared": [],
                }
            _ACC.depth = depth + 1
            return self

        def __exit__(self, exc_type, exc, tb):
            _ACC.depth -= 1
            if _ACC.depth != 0:
                return False
            acc = _ACC.cur
            _ACC.cur = None
            if exc_type is None and notify:
                _flush(session, acc)
            return False

    return _B()


def _flush(session, acc):

    if not acc["prog"]:
        _send_prepared(session, acc)
        if acc["quest"]:
            _quest_track.advance_many(session, acc["quest"])
        return
    n = AchieveNotice()
    n.status = StatusCode.StatusCode_OK
    for aid in acc["order"]:
        a = n.achieves.add()
        a.achieve_id = aid
        a.count = acc["prog"][aid]
    session.send(MsgId.AchieveNotice, n, 0)  # 1720 (多 achieves 同包)
    ts = int(time.time())
    for aid in acc["finished"]:
        f = AchieveFinishNotice()
        f.status = StatusCode.StatusCode_OK
        f.finish_info.achieve_id = aid
        f.finish_info.finish_time = ts
        session.send(MsgId.AchieveFinishNotice, f, 0)  # 1764
    _send_prepared(session, acc)
    if acc["quest"]:

        _quest_track.advance_many(session, acc["quest"])


def prepare_quests(session):
    """对话响应前落实任务及旗标，进度通知保留到动作结束后发送。"""
    acc = _acc()
    if acc is None:
        return
    while acc["quest"]:
        pending = acc["quest"][:]
        acc["quest"].clear()
        result = _quest_track.advance_many(session, pending, send=False)
        if result is not None:
            acc["prepared"].append(result)


def _send_prepared(session, acc):
    for notice, pack in acc["prepared"]:
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
        session.send(MsgId.QuestNotice, notice, 0)


def _finish_once(session, player_id, achieve_id):
    """达成: 防重标记 + AchieveFinishNotice + 任务链推进"""

    if not _quest_track.event_condition_active(player_id, achieve_id):
        return False
    if db.get_kv(player_id, "ach", f"f:{achieve_id}"):
        return False
    db.set_kv(player_id, "ach", f"f:{achieve_id}", 1)
    # 元成就(类型137)以指定成就完成为条件；在同一动作帧内级联，
    # 这样主线/行为成就完成时不会留下永远无法触发的后置成就。
    with batch(session):
        _add_rows(session, 137, 1, match=achieve_id)
    if achieve_id not in finish_notice_ids():
        return True
    if _acc() is not None:
        # 缓冲内: 防重标记照打, 1764 由 _flush 统一补发
        _acc()["finished"].append(achieve_id)
        return True
    n = AchieveFinishNotice()
    n.status = StatusCode.StatusCode_OK
    n.finish_info.achieve_id = achieve_id
    n.finish_info.finish_time = int(time.time())

    session.send(MsgId.AchieveFinishNotice, n, 0)  # 1764
    # 推进以该成就为条件的任务(镜像由 _write->quest_track.advance 完成,
    # 此处不再走旧版 make_QuestNotice 直写 Finish 的路径)
    return True


def add(session, ctype, amount=1, match=None):
    """增量计数(一个动作一条消息: 内部成帧, 全部命中行合并为一份
    AchieveNotice)。rows 匹配规则: 成就无 param 直接计;
    有 param 时须事件携带 match 且 param[0]==match。"""
    with batch(session):
        _add_rows(session, ctype, amount, match)


def _add_rows(session, ctype, amount=1, match=None):
    rows = _index().get(ctype)
    if not rows:
        return
    pid = session.player_id
    for aid, param, target in rows:
        if param and not _matches_param(ctype, aid, param, match):
            continue
        cur = progress(pid, aid)
        repeatable = (
            aid in life_repeat_conditions() or aid in activity_state.period_specs()
        )
        if cur >= target and not repeatable:
            # 事件级重试推进: 旧 make_QuestNotice 每次事件都尝试链推进,
            # 计数已满时(链上晚接受/重放)仍需触发 advance 补救时序
            acc = _acc()
            if acc is None:
                _advance_quest(session, aid)
            elif aid not in acc["quest"]:
                acc["quest"].append(aid)
            continue
        new = cur + max(1, amount)
        if not repeatable:
            new = min(new, target)
        _write(session, pid, aid, new)
        if new >= target:
            _finish_once(session, pid, aid)


_LIFE_REPEAT_CONDITIONS = None


def life_repeat_conditions():
    """生活熟练度条件可重复完成；历史次数仍存同一成就表，不在目标1封顶。"""
    global _LIFE_REPEAT_CONDITIONS
    if _LIFE_REPEAT_CONDITIONS is None:
        _LIFE_REPEAT_CONDITIONS = {
            item["achieve_condition_i_d"]
            for sheet, level_sheet, quest_key in Config.LIFE_ACHIEVE_LIFE_TABLES.values()
            for row in res.get(sheet, {}).get(level_sheet, {}).get("datas", ())
            for item in row.get(quest_key, ())
            if item.get("complete_limit")
        }
    return _LIFE_REPEAT_CONDITIONS


def _matches_param(ctype, achieve_id, param, match):
    """判断事件对象是否命中成就参数。

    大多数条件只带一个对象 id；副本宝箱条件还带第二个类别值，
    通过 tuple 前缀匹配支持这类条件，同时保留对话条件第二列和
    条件 id 直报的历史口径。
    """
    if match is None:
        return False
    if isinstance(match, (tuple, list)):
        wanted = tuple(match)
        return len(param) >= len(wanted) and tuple(param[: len(wanted)]) == wanted
    return (
        param[0] == match
        or (ctype in (37, 40) and len(param) > 1 and param[1] == match)
        or achieve_id == match
    )


_AIDS = None


def _aid_table():
    """i_d -> (param, target) 全表按成就 id 索引(add_by_id 用)"""
    global _AIDS
    if _AIDS is None:
        t = {}
        for rows in _index().values():
            for aid, param, target in rows:
                t[aid] = (param, target)
        _AIDS = t
    return _AIDS


def add_by_id(session, achieve_id, amount=1):
    """按成就条件 id 直报计数(单动作一条消息: 内部成帧)。"""
    with batch(session):
        _add_by_id_row(session, achieve_id, amount)


def _add_by_id_row(session, achieve_id, amount=1):
    """官服/HEAD 口径: NpcTalk 等事件可直接携带条件 id,
    该条件可能不属事件对应类型族, 如对话上报抽卡类 11000131。"""
    e = _aid_table().get(achieve_id)
    if not e:
        return
    _param, target = e
    pid = session.player_id
    cur = progress(pid, achieve_id)
    if cur >= target:
        acc = _acc()
        if acc is None:
            _advance_quest(session, achieve_id)
        elif achieve_id not in acc["quest"]:
            acc["quest"].append(achieve_id)
        return
    new = min(cur + max(1, amount), target)
    _write(session, pid, achieve_id, new)
    if new >= target:
        _finish_once(session, pid, achieve_id)


def captain_id(player_id):
    """当前队长(队伍第一位)角色 id; 取不到返回 0"""

    row = db.get_players_info(player_id, "team")
    if not row:
        return 0
    team = row[0]
    if isinstance(team, str):
        first = team.split(",")[0].strip()
        return int(first) if first.isdigit() else 0
    if isinstance(team, (list, tuple)) and team:
        first = team[0]
        if isinstance(first, str) and not first.strip().isdigit():
            return 0
        return int(first)
    return 0


def captain_level(session, level):
    """队长等级36(状态型): 队长当前等级 >= count_param 即达成"""
    with batch(session):
        _captain_level_rows(session, level)


def _captain_level_rows(session, level):
    rows = _index().get(36) or ()
    pid = session.player_id
    for aid, param, target in rows:
        want = min(level, target)
        if want > progress(pid, aid):
            _write(session, pid, aid, want)
        if level >= target:
            _finish_once(session, pid, aid)


def character_level_count(session):
    """N个角色等级达到X级79: param=(X,), count_param=角色数"""
    with batch(session):
        _character_level_count_rows(session)


def _character_level_count_rows(session):
    rows = _index().get(79) or ()
    if not rows:
        return

    pid = session.player_id
    levels = []
    for blob in db.get_characters(pid):
        c = PbChar()
        c.ParseFromString(blob)
        levels.append(int(c.level))
    for aid, param, target in rows:
        need_lv = param[0] if param else 1
        cnt = sum(1 for lv in levels if lv >= need_lv)
        cur = progress(pid, aid)
        if cnt >= target and cur < target:
            _write(session, pid, aid, target)
            _finish_once(session, pid, aid)
        elif cur < cnt < target:
            _write(session, pid, aid, cnt)


def set_state(session, ctype, value, match=None):
    """状态型成就: value >= count_param 且参数命中时达成。"""
    with batch(session):
        _set_state_rows(session, ctype, value, match=match)


def _set_state_rows(session, ctype, value, match=None):
    rows = _index().get(ctype)
    if not rows:
        return
    pid = session.player_id
    for aid, param, target in rows:
        if param and not _matches_param(ctype, aid, param, match):
            continue
        if value >= target and progress(pid, aid) < target:
            _write(session, pid, aid, target)
            _finish_once(session, pid, aid)


def _bump_world_counter(session, sub, world, amount=1):

    key = f"w:{sub}:{world}"
    cur = int(db.get_kv(session.player_id, "ach", key) or 0)
    db.set_kv(session.player_id, "ach", key, cur + amount)
    return cur + amount


def _scope_of(session):
    """(世界号, 子场景id): scene 仅在玩家处于子场景(>=1000)时给出"""
    sid = getattr(session, "scene_id", 0) or 0
    if sid <= 0:
        return None, None
    if sid < 100:
        return sid, None
    return (sid // 1000) or None, sid


def _finish_scoped_split(session, ctype, world, scene, wcnt, scnt):
    """作用域计数同步到通用 Achieve 记录并判定完成:
    - param 缺省: 仅看 wcnt 是否达标;
    - param < 1000(世界行): p0 == world 且 wcnt 达标;
    - param >= 1000(场景行): p0 == scene 且 scnt 达标
      (如 锅中寻宝1002/水晶球圣诞老人的礼物1001, 兄弟子场景互不串计)。"""
    rows = _index().get(ctype) or ()
    pid = session.player_id
    for aid, param, target in rows:
        p0 = param[0] if param else None
        if p0 is None:
            cnt = wcnt
        elif p0 >= 1000:
            if not scene or p0 != scene:
                continue
            cnt = scnt
        else:
            if p0 != world:
                continue
            cnt = wcnt
        cur = progress(pid, aid)
        new = min(cnt, target)
        if new > cur:
            _write(session, pid, aid, new)
        if cnt >= target:
            _finish_once(session, pid, aid)


Config.ACHIEVE_TRACK_SCOPED_COUNTER_PREFIX.update(
    {ctype: f"m{ctype}" for ctype in (101, 102, 103, 105, 106, 107, 108, 109, 110, 111)}
)


def sync_scoped_progress(session, achieve_ids=None):
    """将历史作用域计数回填到通用 Achieve 记录。

    旧版本只在作用域成就达标时写 Achieve.count, 当前事件更新已会逐次
    写入; 此同步让升级前保存在 player_kv 的世界/场景进度在查询时可见。
    """
    wanted = set(achieve_ids) if achieve_ids is not None else None
    with batch(session):
        pid = session.player_id
        for ctype, prefix in Config.ACHIEVE_TRACK_SCOPED_COUNTER_PREFIX.items():
            for aid, param, target in _index().get(ctype) or ():
                if wanted is not None and aid not in wanted:
                    continue
                if not param:
                    continue
                scope = param[0]
                count = int(db.get_kv(pid, "ach", f"w:{prefix}:{scope}") or 0)
                current = progress(pid, aid)
                new = min(count, target)
                if new > current:
                    _write(session, pid, aid, new)
                if count >= target:
                    _finish_once(session, pid, aid)


def _finish_scoped_rows(session, ctype, world, counter):
    """兼容入口: 仅世界计数器(无子场景上下文)"""
    _finish_scoped_split(session, ctype, world, None, counter, 0)


def collection(session, sub, amount=1, coll_type=None):
    """场景收集/照片/水晶等世界级归因事件。"""
    world, scene = _scope_of(session)
    if not world:
        return
    wcnt = _bump_world_counter(session, sub, world, amount)
    scnt = _bump_world_counter(session, sub, scene, amount) if scene else 0
    t = Config.SUBTYPE_TO_TYPE.get(sub)
    bt = Config.BADGE_SUB_TYPE.get(sub)
    # 任务侧同源类型: 传送点100/141；区域装置99由 AreaUnlock 事件计数。
    extras = {"portal": (100, 141)}.get(sub, ())
    for ct in (t, bt, *extras):
        if ct:
            _finish_scoped_split(session, ct, world, scene, wcnt, scnt)
    # 探索度: 按不可再生收集点位比例推进
    explore_collect(session, coll_type)


def scenic(session, flag_id):
    """景点旗标解锁(仅普通手册点调用): 按 Flag.scene_i_d 归一世界计数
    (子场景 1001~1003 归入所属世界, 避免世界行 param=(1~5) 无法匹配)。"""
    scene = None
    for f in res.get("Flag", {}).get("flag", {}).get("datas", []):
        if isinstance(f, dict) and f.get("i_d") == flag_id:
            scene = f.get("scene_i_d")
            break
    if scene is None:
        w, s = _scope_of(session)
        scene = s or w
    if not scene:
        return
    # 子场景归入所属世界聚合(1002→1)
    world = scene if scene < 100 else ((scene // 1000) or None)
    if not world:
        return
    cnt = _bump_world_counter(session, "scenic", world)
    _finish_scoped_rows(session, 11, world, cnt)
    _finish_scoped_rows(session, 96, world, cnt)
    _finish_scoped_rows(session, 142, world, cnt)


_SCENE_TOTALS = None
_POINT_OWNER = {}


def _attainable_index():
    """懒构建点位所属场景索引，探索分母始终读取Scene.scene_progress。"""
    global _SCENE_TOTALS, _POINT_OWNER
    if _SCENE_TOTALS is None:
        totals = {}
        owners = {}
        ctb_ids = {
            e.get("i_d")
            for e in res.get("TreasureBox", {})
            .get("collection_treasure_box", {})
            .get("datas", ())
            if isinstance(e, dict) and tuple(e.get("refresh_time") or ()) == (0,)
        }
        ci_ids = {
            r.get("i_d")
            for r in res.get("CollectionItem", {})
            .get("collection_item", {})
            .get("datas", ())
            if isinstance(r, dict)
        }
        flag_points = {}
        for m in res.get("Manual", {}).get("manual_dungeon", {}).get("datas", ()):
            for it in m.get("manual_dungeon_items", ()) or ():
                fid = it.get("flag_i_d")
                if fid and it.get("transfer_scene_i_d"):
                    flag_points[fid] = it["transfer_scene_i_d"]
        for sc in res.get("ScenesConfigAsset", {}).get("Scenes", ()):
            if not isinstance(sc, dict):
                continue
            att = set()
            for c in sc.get("CollectionTreasureInfos") or ():
                pid = c.get("ID") if isinstance(c, dict) else None
                if not pid:
                    continue
                if pid in ctb_ids or int(f"10{pid}") in ci_ids:
                    att.add(pid)
            if att:
                totals[sc["ID"]] = len(att)
                for p in att:
                    owners.setdefault(p, sc["ID"])
        # 秘境发现点: 归属 transfer_scene_i_d 所在块
        # (若与既有收集点位重合则不重复计入分母)
        for fid, blk in flag_points.items():
            if fid not in owners:
                owners[fid] = blk
                totals[blk] = totals.get(blk, 0) + 1
        _SCENE_TOTALS = {
            row["i_d"]: sum(
                entry.get("total", 0) for entry in row.get("scene_progress_info") or ()
            )
            for row in res["Scene"]["scene_progress"]["datas"]
            if isinstance(row, dict) and row.get("i_d")
        }
        _POINT_OWNER = owners
    return _SCENE_TOTALS


def _scene_totals():
    """各场景配置的探索点数总量。"""
    return _attainable_index()


def explore_flag(session, flag_id):
    """秘境**首次发现解锁**(ManualFlagUnlock)计入所属场景探索度;
    通关/进入副本不计数, efp:<flag> 幂等去重。"""
    with batch(session):
        _explore_flag_impl(session, flag_id)


def _explore_flag_impl(session, flag_id):

    _attainable_index()
    block = _POINT_OWNER.get(flag_id)
    if not block:
        return
    flag = f"efp:{flag_id}"
    if db.get_kv(session.player_id, "ach", flag):
        return
    db.set_kv(session.player_id, "ach", flag, 1)
    key = f"exp:{block}"
    cur = int(db.get_kv(session.player_id, "ach", key) or 0)
    if cur < _SCENE_TOTALS.get(block, 0):
        db.set_kv(session.player_id, "ach", key, cur + 1)
    _refresh_degree(session)


def explore_box_open(session, box_id=None):
    """一次性收集宝箱开启: 与 Collecting 同口径计入场景探索度。

    box_id 命中本场景不可再生点位(TreasureBox.collection_treasure_box
    refresh_time==[0] 或 ScenesConfigAsset.CollectionTreasureInfos)时计数。"""
    with batch(session):
        _explore_box_open_impl(session, box_id)


def _explore_box_open_impl(session, box_id=None):

    scene = getattr(session, "scene_id", 0) or 0
    totals = _scene_totals()
    if scene not in totals:
        return
    if box_id is not None and not _is_scene_point(scene, box_id):
        return
    key = f"exp:{scene}"
    cur = int(db.get_kv(session.player_id, "ach", key) or 0)
    if cur < totals[scene]:
        db.set_kv(session.player_id, "ach", key, cur + 1)
    _refresh_degree(session)


_SCENE_POINTS = None


def _is_scene_point(scene, box_id):
    """box_id 是否为该场景的收集点位(一次性宝箱)"""
    global _SCENE_POINTS
    if _SCENE_POINTS is None:
        pts = {}
        for sc in res.get("ScenesConfigAsset", {}).get("Scenes", ()):
            if not isinstance(sc, dict):
                continue
            for c in sc.get("CollectionTreasureInfos") or ():
                if isinstance(c, dict) and c.get("ID"):
                    pts.setdefault(c["ID"], sc["ID"])
        _SCENE_POINTS = pts
    return _SCENE_POINTS.get(box_id) == scene or _POINT_OWNER.get(box_id) == scene


def explore_collect(session, coll_type=None):
    """Collecting 成功后调用: 不可再生收集品计数并刷新探索度。"""
    with batch(session):
        _explore_collect_impl(session, coll_type)


def _explore_collect_impl(session, coll_type=None):

    scene = getattr(session, "scene_id", 0) or 0
    totals = _scene_totals()
    if scene not in totals:
        return
    if coll_type is not None and coll_type not in Config.EXPLORE_COLL_TYPES:
        return
    key = f"exp:{scene}"
    cur = int(db.get_kv(session.player_id, "ach", key) or 0)
    if cur < totals[scene]:
        db.set_kv(session.player_id, "ach", key, cur + 1)
    _refresh_degree(session)


def _degree(player_id, scene_ids):
    """场景探索度(万分比)，分母使用资源表的场景进度总数。"""

    totals = _scene_totals()
    got = tot = 0
    for sc in scene_ids:
        t = totals.get(sc)
        if not t:
            continue
        tot += t
        got += min(int(db.get_kv(player_id, "ach", f"exp:{sc}") or 0), t)
    if not tot:
        return 0
    return min(10000, got * 10000 // tot)


def _refresh_degree(session):
    """类型113(场景/世界完成度): 达标即完成并推进相关任务"""
    rows = _index().get(113) or ()
    if not rows:
        return
    pid = session.player_id
    cache = {}
    for aid, param, target in rows:
        p = param[0] if param else None
        if p in cache:
            deg = cache[p]
        else:
            # 世界号(1~5)优先聚合其场景组; 其余 param 视作具体场景 id
            scenes = (p,) if p in _scene_totals() else Config.WORLD_SCENES.get(p, ())
            deg = _degree(pid, scenes) if scenes else -1
            cache[p] = deg
        value = min(deg, target)
        if value > progress(pid, aid):
            _write(session, pid, aid, value)
            if value >= target:
                _finish_once(session, pid, aid)


def daily_login(session):
    """每日登录(类型 82): 每自然日一次"""
    with batch(session):
        _daily_login_impl(session)


def _daily_login_impl(session):

    day = str(day_index())
    if db.get_kv(session.player_id, "ach", "login_day") == day:
        return
    db.set_kv(session.player_id, "ach", "login_day", day)
    add(session, 82)


def gather(session, item_id, amount=1, gather_type=None):
    """采集产出归因: 基础次数成就 + 世界级聚合(单动作一条消息)"""
    with batch(session):
        _gather_impl(session, item_id, amount, gather_type=gather_type)


def _gather_impl(session, item_id, amount=1, gather_type=None):
    base = int(item_id) // 100000 if item_id else 0
    basic = Config.ACHIEVE_TRACK_GATHER_ACTION_TYPE.get(gather_type)
    _fallback_basic, badge_t, sub = Config.GATHER_PREFIX.get(base, (None, None, None))
    if basic is None:
        basic = _fallback_basic
    if basic:
        # 类型61~66统计采集动作，不统计幸运奖励一次发出的多个物品。
        add(session, basic)
    exact_type = {202: 68, 203: 69, 205: 71}.get(base)
    if exact_type:
        add(session, exact_type, amount, match=item_id)
    if sub:
        world, scene = _scope_of(session)
        if world:
            wcnt = _bump_world_counter(session, sub, world)
            scnt = _bump_world_counter(session, sub, scene) if scene else 0
            if badge_t:
                _finish_scoped_split(session, badge_t, world, scene, wcnt, scnt)


def add_scoped_count(session, ctype, world=None):
    """按世界/场景计数并判定(如 106消灭当前世界灰物 / 3开箱 /
    101竞速挑战 / 102世界挑战): 场景行(param>=1000)按当前子场景精确计数。"""
    with batch(session):
        _add_scoped_count_impl(session, ctype, world)


def _add_scoped_count_impl(session, ctype, world=None):
    w, scene = _scope_of(session)
    if w is None:
        w = world
    if not w:
        return
    prefix = f"m{ctype}"
    wcnt = _bump_world_counter(session, prefix, w)
    scnt = _bump_world_counter(session, prefix, scene) if scene else 0
    _finish_scoped_split(session, ctype, w, scene, wcnt, scnt)


def report(session, event, *, match=None, amount=1, **fields):
    """事件计数统一入口: 一个动作只构造一条消息
    (全部命中成就合并为一份 AchieveNotice, 任务推进合并为一份 QuestNotice)。"""
    with batch(session):
        _report_ops(session, event, match=match, amount=amount, **fields)


def _report_ops(session, event, *, match=None, amount=1, **fields):
    """事件计数统一入口(handler 侧不出现条件类型数字)。

    事件名决定归属的条件族, 由模块自行扫表判定哪些成就行命中:
    如 report(session, "kill", match=怪物id) 一次记录该怪在 1/4/6/41/42
    族里的全部"讨伐[该怪]"成就(14010001 及同段全部), 并同步 86/106 全局计数。
    match 为事件携带的对象 id(怪物/物品/节点/场景等), amount 为增量。
    """
    if event == "talk":
        add(session, 37, amount, match=match)
        add(session, 40, amount, match=match)
        if match is not None:
            add_by_id(session, match, amount)
        return
    if event == "archaeology_collect":
        ctype = Config.ARCHAEOLOGY_TYPE_TO_CONDITION.get(fields.get("archaeology_type"))
        if ctype is not None:
            add(session, ctype, amount)
        return
    if event == "gather":
        add(session, 28, amount, match=match)
        gather(session, match, amount, gather_type=fields.get("wt"))
        add(session, 67, 1, match=match)
        ct = Config.ACHIEVE_TRACK_GATHER_CAT_SCOPED.get(fields.get("wt"))
        if ct:
            add_scoped_count(session, ct)
        return
    if event == "learn_life_skill":
        add(
            session,
            Config.ACHIEVE_TRACK_LIFE_LEARN_TYPE.get(fields.get("life_type"), 159),
        )
        return
    if event == "dungeon_box":
        dungeon_id = fields.get("dungeon_id")
        box_kind = fields.get("box_kind")
        if box_kind == "yellow":
            add(session, 34, amount, match=dungeon_id)
        elif box_kind == "normal":
            add(session, 167, amount, match=(dungeon_id, 1))
        return
    if event == "battle_finish":
        row = db.get_players_info(session.player_id, "team")
        if not row:
            return
        team = row[0]
        if not isinstance(team, (list, tuple)):
            return
        team_ids = [character_id for character_id in team if character_id]
        for character_id in team_ids:
            add(session, 88, amount, match=character_id)
        if team_ids:
            add(session, 89, amount, match=team_ids[0])
        return
    ops = Config.ACHIEVE_TRACK_EVENTS.get(event)
    if ops is None:
        log.warning("achieve report: 未注册事件 %s", event)
        return
    for mode, ctype, mf, af in ops:
        m = match if mf is None else fields.get(mf)
        a = amount if af is None else fields.get(af, 1)
        if mode == "scoped":
            add_scoped_count(session, ctype)
        elif mode == "state":
            set_state(session, ctype, m, match=match)
        else:
            add(session, ctype, a, match=m)
    if event == "kill" and fields.get("monster_tag") == 3:
        # 条件33的 param 不是怪物 id，而是 Monster.new_tag=3(BOSS)。
        add(session, 33, amount, match=3)
    if event == "dungeon_finish":
        mission_type = fields.get("mission_type")
        if mission_type == 5:
            add(session, 116)
        elif mission_type == 12:
            add(session, 117)


_TARGETS = None


def target_of_all():
    """全量 {achieve_id: count_param}"""
    global _TARGETS
    if _TARGETS is None:
        t = {}
        for rows in _index().values():
            for aid, _param, target in rows:
                t[aid] = target
        _TARGETS = t
    return _TARGETS


def target_of(achieve_id):
    """成就目标次数(Achieve.count_param); 未配置返回 None"""
    return target_of_all().get(achieve_id)


_LIFE_REWARDS = None


def life_reward_index():
    """生活成就奖励登记: {achieve_id: (reward_i_d, 目标次数)}。

    来源(对表验证): Fishing.fish_achieve_rewards / Make.make_achieve_rewards /
    Spin.spin_achieve_rewards / Handicraft.handicraft_achieve_rewards /
    LifeGather.life_gather_achieve_rewards —— 均为
    {achieve_condition_i_d, reward_i_d}, 目标次数取 Achieve.count_param。
    对应成就条件类型为 28(获取[item]xN), 进度由本模块 add(28, match=item) 计数。
    """
    global _LIFE_REWARDS
    if _LIFE_REWARDS is None:
        idx = {}
        sheets = (
            ("Fishing", "fishing_info", "fish_achieve_rewards"),
            ("Make", "make_item", "make_achieve_rewards"),
            ("Spin", "spin_item", "spin_achieve_rewards"),
            ("Handicraft", "handicraft_item", "handicraft_achieve_rewards"),
            ("LifeGather", "life_gather_item", "life_gather_achieve_rewards"),
        )
        targets = target_of_all()
        for sheet, sub, key in sheets:
            for row in res.get(sheet, {}).get(sub, {}).get("datas", ()):
                if not isinstance(row, dict):
                    continue
                for e in row.get(key, ()) or ():
                    if not isinstance(e, dict):
                        continue
                    aid = e.get("achieve_condition_i_d")
                    rid = e.get("reward_i_d")
                    if aid and rid:
                        idx[aid] = (rid, targets.get(aid, 1))
        _LIFE_REWARDS = idx
    return _LIFE_REWARDS
