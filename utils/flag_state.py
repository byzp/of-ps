"""玩家场景旗标状态及通知。"""

from config import Config

from network.msg_id import MsgId
from proto.net_pb2 import FlagUnlockAddNotice, FlagUnLockRemoveNotice, StatusCode

import utils.db as db
from utils import flag_config


def _read_ids(player_id, namespace):
    raw = db.get_kv(player_id, namespace, "ids", b"")
    if not raw:
        return set()
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError("flag ids must be bytes")
    return {int(value) for value in raw.decode().split(",") if value}


def _write_ids(player_id, namespace, values):
    db.set_kv(
        player_id,
        namespace,
        "ids",
        ",".join(str(value) for value in sorted(values)).encode(),
    )


def get_ids(player_id, namespace):
    return _read_ids(player_id, namespace)


def notify_added(session, flag_ids):
    if not flag_ids:
        return
    notice = FlagUnlockAddNotice()
    notice.status = StatusCode.StatusCode_OK
    notice.flag_ids.extend(flag_ids)
    session.send(MsgId.FlagUnlockAddNotice, notice, 0)


def unlock_flags(session, flag_ids, namespace=Config.SCENE_FLAGS_NS, notify=True):
    current = _read_ids(session.player_id, namespace)
    added = []
    for flag_id in flag_ids:
        if flag_id and flag_id not in current:
            current.add(flag_id)
            added.append(flag_id)
    if not added:
        return added

    _write_ids(session.player_id, namespace, current)
    if notify:
        notify_added(session, added)
    return added


def unlock_for_quest(session, quest):
    condition_ids = [condition.condition_id for condition in quest.conditions]
    flag_ids = flag_config.flag_ids_for_conditions(condition_ids)
    return unlock_flags(session, flag_ids)


def finish_quest(session, quest):
    """任务结束时撤掉临时战斗入口，包括通过对话跳过战斗的分支。"""
    condition_ids = [condition.condition_id for condition in quest.conditions]
    candidates = set(flag_config.flag_ids_for_conditions(condition_ids))
    visible = _read_ids(session.player_id, Config.SCENE_FLAGS_NS)
    removed = [
        row["i_d"]
        for row in flag_config.flag_rows()
        if row["i_d"] in candidates & visible and row.get("icon_i_d") == 1
    ]
    if removed:
        remove_scene_flags(session.player_id, removed)
        notice = FlagUnLockRemoveNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.flag_ids.extend(removed)
        session.send(MsgId.FlagUnLockRemoveNotice, notice, 0)


def remove_scene_flags(player_id, flag_ids):
    current = _read_ids(player_id, Config.SCENE_FLAGS_NS)
    removed = False
    for flag_id in flag_ids:
        if flag_id in current:
            current.remove(flag_id)
            removed = True
    if removed:
        _write_ids(player_id, Config.SCENE_FLAGS_NS, current)


def _battle_finished(player_id, flag_id):
    row = next((row for row in flag_config.flag_rows() if row["i_d"] == flag_id), None)
    if not row or row.get("icon_i_d") not in (1, 2):
        return False  # 景点播放后入口保留，完成状态另由SceneData.flags回放。
    for relation_id in flag_config.flag_relations(flag_id):
        if db.get_kv(player_id, "flag_battle", f"b:{relation_id}", 0):
            return True
    return False


def is_battle_finished(player_id, flag_id):
    return _battle_finished(player_id, flag_id)


def visible_ids(player_id):
    result = _read_ids(player_id, Config.MANUAL_FLAGS_NS)
    result.update(_read_ids(player_id, Config.SCENE_FLAGS_NS))
    return {flag_id for flag_id in result if not _battle_finished(player_id, flag_id)}
