"""动作/舞蹈/表情动作的永久解锁。

客户端有两套动作来源：
  1. ActionStudy（学习他人动作）→ AchieveActionUnLockNotice.study_action，带过期时间；
  2. 直接获得道具（如「舞蹈B」713285）→ AchieveActionUnLockNotice.action_id_lst，永久。
本模块负责第 2 条：把 tag=12 且 id>=710000 的动作道具映射成 action_id 并持久化。

映射规则：action_id = item_id - 710000（已用 Action.action_info 全表校验，
713005→3005 ... 713295→3295 全部命中）。
"""

from network.msg_id import MsgId
from proto.net_pb2 import AchieveActionUnLockNotice, StatusCode

import utils.db as db
from utils.res_loader import res

NS = "actions_perm"
KEY = "ids"
OFFSET = 710000

__all__ = [
    "action_of_item",
    "perm_ids",
    "add_perms",
    "send_perm_notice",
    "build_notice",
]

_action_cache = None


def _action_ids():
    global _action_cache
    if _action_cache is None:
        _action_cache = {
            a["i_d"]
            for a in res.get("Action", {}).get("action_info", {}).get("datas", [])
            if isinstance(a, dict) and a.get("i_d")
        }
    return _action_cache


def action_of_item(item_id) -> int:
    """道具 id → 动作 id，不是动作道具则返回 0。"""
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return 0
    if item_id <= OFFSET:
        return 0
    aid = item_id - OFFSET
    return aid if aid in _action_ids() else 0


def perm_ids(player_id) -> list:
    """该玩家已永久解锁的动作 id（升序）。"""
    raw = db.get_kv(player_id, NS, KEY, b"")
    if not raw:
        return []
    out = []
    for part in raw.decode().split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return sorted(set(out))


def add_perms(player_id, action_ids) -> list:
    """写入永久解锁；返回本次真正新增的动作 id。"""
    want = {int(a) for a in action_ids if int(a) > 0}
    if not want:
        return []
    have = set(perm_ids(player_id))
    new = sorted(want - have)
    if new:
        db.set_kv(player_id, NS, KEY, ",".join(str(a) for a in sorted(have | want)).encode())
    return new


def build_notice(action_ids) -> AchieveActionUnLockNotice:
    notice = AchieveActionUnLockNotice()
    notice.status = StatusCode.StatusCode_OK
    for aid in action_ids:
        notice.action_id_lst.append(int(aid))
    return notice


def send_perm_notice(session, action_ids=None, packet_id=0):
    """给客户端推「永久解锁动作」通知；action_ids 为空则发全部已解锁。"""
    ids = list(action_ids) if action_ids else perm_ids(session.player_id)
    if not ids:
        return 0
    session.send(MsgId.AchieveActionUnLockNotice, build_notice(ids), 0)
    return len(ids)
