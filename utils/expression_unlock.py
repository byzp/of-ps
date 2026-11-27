"""聊天表情(tag=40 道具)的永久解锁。

与动作(tag=12)不同，聊天表情走 ChatUnLockExpressionNotice(1940)，
客户端 `PlayerSystem.UpdateChatEmotion` → `PlayerModel.UpdateExpression(expressionId_)`。

映射：表情道具 id 直接就是 Chat.chat_emotion 的 i_d
（251 个 tag=40 道具里有 246 个能在 chat_emotion 表命中，其余 5 个是活动占位）。
Lolo 的实现同样直接拿 item id 当 expression id（game/model/chat.go AddUnExpression）。
"""

from network.msg_id import MsgId
from proto.net_pb2 import ChatUnLockExpressionNotice, StatusCode

import utils.db as db
from utils.res_loader import res

NS = "expr_perm"
KEY = "ids"

__all__ = [
    "is_expression_item",
    "expression_of_item",
    "perm_ids",
    "add_perms",
    "build_notice",
    "send_perm_notice",
]

_expr_ids = None
_tag40 = None


def _expression_ids():
    global _expr_ids
    if _expr_ids is None:
        _expr_ids = {
            r["i_d"]
            for r in res.get("Chat", {}).get("chat_emotion", {}).get("datas", [])
            if isinstance(r, dict) and r.get("i_d")
        }
    return _expr_ids


def _tag40_ids():
    global _tag40
    if _tag40 is None:
        _tag40 = {
            r["i_d"]
            for r in res.get("Item", {}).get("item", {}).get("datas", [])
            if isinstance(r, dict) and r.get("new_bag_item_tag") == 40 and r.get("i_d")
        }
    return _tag40


def is_expression_item(item_id) -> bool:
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return False
    return item_id in _tag40_ids()


def expression_of_item(item_id) -> int:
    """表情道具 id → 表情 id；不是表情道具返回 0。"""
    item_id = int(item_id)
    if item_id not in _tag40_ids():
        return 0
    return item_id if item_id in _expression_ids() else 0


def perm_ids(player_id) -> list:
    raw = db.get_kv(player_id, NS, KEY, b"")
    if not raw:
        return []
    out = []
    for part in raw.decode().split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return sorted(set(out))


def add_perms(player_id, expression_ids) -> list:
    want = {int(e) for e in expression_ids if int(e) > 0}
    if not want:
        return []
    have = set(perm_ids(player_id))
    new = sorted(want - have)
    if new:
        db.set_kv(
            player_id, NS, KEY, ",".join(str(e) for e in sorted(have | want)).encode()
        )
    return new


def build_notice(expression_ids) -> ChatUnLockExpressionNotice:
    notice = ChatUnLockExpressionNotice()
    notice.status = StatusCode.StatusCode_OK
    for eid in expression_ids:
        notice.expression_id.append(int(eid))
    return notice


def send_perm_notice(session, expression_ids=None) -> int:
    """推「解锁表情」通知；不传则发该玩家全部已解锁表情。"""
    ids = list(expression_ids) if expression_ids else perm_ids(session.player_id)
    if not ids:
        return 0
    session.send(MsgId.ChatUnLockExpressionNotice, build_notice(ids), 0)
    return len(ids)
