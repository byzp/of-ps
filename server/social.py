"""好友、黑名单和私聊的一致性与持久化入口。

关系仍使用 ``friend`` 表的两条有向记录：
``player_id -> friend_id`` 的 0/1/2/3 分别表示无关系/待接受/好友/拉黑。
跨玩家操作统一按 ID 排序获取玩家锁，再进入数据库事务；网络通知由
handler 在事务提交后发送。
"""

from contextlib import ExitStack, contextmanager
import pickle
import time

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import (
    FriendHandleNotice,
    FriendHandleType,
    StatusCode,
)

import utils.db as db
from utils import item_mgr


FRIEND_NONE = 0
FRIEND_APPLY = 1
FRIEND_OK = 2
FRIEND_BLACK = 3

_PRIVATE_HISTORY_NS = "chat_private"
_PRIVATE_UNREAD_NS = "chat_private_unread"
_PRIVATE_OPERATION_NS = "chat_private_operations"


@contextmanager
def player_locks(*player_ids):
    """按固定顺序持有玩家锁，避免双向请求互相死锁。"""
    with ExitStack() as stack:
        for player_id in sorted(set(player_ids)):
            stack.enter_context(item_mgr.player_lock(player_id))
        yield


@contextmanager
def relation_transaction(*player_ids):
    """社交写操作的锁顺序：玩家锁 -> DB transaction。"""
    with player_locks(*player_ids):
        with db.transaction():
            yield


def pair_key(first_id, second_id):
    first_id, second_id = sorted((first_id, second_id))
    return f"{first_id}:{second_id}"


def _valid_pair(first_id, second_id):
    return first_id > 0 and second_id > 0 and first_id != second_id


def _player_exists(player_id):
    return bool(db.get_players_info(player_id, "player_id"))


def _status(player_id, friend_id):
    return db.get_friend_info(player_id, friend_id, "friend_status")[0]


def _set_status(player_id, friend_id, status):
    db.set_friend_info(player_id, friend_id, "friend_status", status)


def request_friend(sender_id, target_id):
    """返回 ``(status, new_application)``，重复申请不写状态、不发通知。"""
    with relation_transaction(sender_id, target_id):
        if not _valid_pair(sender_id, target_id) or not _player_exists(target_id):
            return StatusCode.StatusCode_PLAYER_NOT_FOUND, False

        sender_status = _status(sender_id, target_id)
        target_status = _status(target_id, sender_id)
        if FRIEND_BLACK in (sender_status, target_status):
            return StatusCode.StatusCode_FRIEND_BLACK, False
        if FRIEND_OK in (sender_status, target_status):
            return StatusCode.StatusCode_FRIEND_EXIST, False
        # 任意一条待申请记录都表示双方之间已有申请，包括反向申请。
        if FRIEND_APPLY in (sender_status, target_status):
            return StatusCode.StatusCode_FRIEND_APPLY_EXIST, False

        db.init_friend(sender_id, target_id)
        _set_status(target_id, sender_id, FRIEND_APPLY)
        return StatusCode.StatusCode_OK, True


def handle_friend(recipient_id, applicant_id, agree):
    """返回 ``(status, accepted)``；只有待接收方能够接受或拒绝。"""
    with relation_transaction(recipient_id, applicant_id):
        if not _valid_pair(recipient_id, applicant_id) or not _player_exists(applicant_id):
            return StatusCode.StatusCode_PLAYER_NOT_FOUND, False

        recipient_status = _status(recipient_id, applicant_id)
        applicant_status = _status(applicant_id, recipient_id)
        if FRIEND_BLACK in (recipient_status, applicant_status):
            return StatusCode.StatusCode_FRIEND_BLACK, False

        incoming = recipient_status == FRIEND_APPLY and applicant_status in (
            None,
            FRIEND_NONE,
        )
        if not incoming:
            return StatusCode.StatusCode_FRIEND_NOT_APPLY, False

        db.init_friend(recipient_id, applicant_id)
        if agree:
            _set_status(recipient_id, applicant_id, FRIEND_OK)
            _set_status(applicant_id, recipient_id, FRIEND_OK)
            return StatusCode.StatusCode_OK, True

        _set_status(recipient_id, applicant_id, FRIEND_NONE)
        _set_status(applicant_id, recipient_id, FRIEND_NONE)
        return StatusCode.StatusCode_OK, False


def remove_friend(actor_id, target_id):
    """返回 ``(status, removed)``，保留聊天历史和未读状态。"""
    with relation_transaction(actor_id, target_id):
        if not _valid_pair(actor_id, target_id) or not _player_exists(target_id):
            return StatusCode.StatusCode_PLAYER_NOT_FOUND, False

        actor_status = _status(actor_id, target_id)
        target_status = _status(target_id, actor_id)
        if actor_status != FRIEND_OK and target_status != FRIEND_OK:
            return StatusCode.StatusCode_OK, False

        db.init_friend(actor_id, target_id)
        # 删除好友不能顺带解除任何一方的拉黑。
        if actor_status != FRIEND_BLACK:
            _set_status(actor_id, target_id, FRIEND_NONE)
        if target_status != FRIEND_BLACK:
            _set_status(target_id, actor_id, FRIEND_NONE)
        return StatusCode.StatusCode_OK, True


def set_blacklist(actor_id, target_id, remove):
    """返回 ``(status, friendship_removed)``。

    两条 3 记录可以同时存在，分别保留双方自己的拉黑选择；解除时只改
    发起方那条记录。好友或待申请关系则会被当前拉黑方原子切断。
    """
    with relation_transaction(actor_id, target_id):
        if not _valid_pair(actor_id, target_id) or not _player_exists(target_id):
            return StatusCode.StatusCode_PLAYER_NOT_FOUND, False

        actor_status = _status(actor_id, target_id)
        target_status = _status(target_id, actor_id)
        if remove:
            if actor_status != FRIEND_BLACK:
                return StatusCode.StatusCode_OK, False
            db.init_friend(actor_id, target_id)
            removed = target_status == FRIEND_OK
            _set_status(actor_id, target_id, FRIEND_NONE)
            if target_status == FRIEND_OK:
                _set_status(target_id, actor_id, FRIEND_NONE)
            return StatusCode.StatusCode_OK, removed

        removed = FRIEND_OK in (actor_status, target_status)
        db.init_friend(actor_id, target_id)
        _set_status(actor_id, target_id, FRIEND_BLACK)
        if target_status != FRIEND_BLACK:
            _set_status(target_id, actor_id, FRIEND_NONE)
        return StatusCode.StatusCode_OK, removed


def private_chat_status(first_id, second_id):
    """私聊权限要求双向好友，且任意一方拉黑都优先拒绝。"""
    if not _valid_pair(first_id, second_id) or not _player_exists(second_id):
        return StatusCode.StatusCode_PLAYER_NOT_FOUND
    first_status = _status(first_id, second_id)
    second_status = _status(second_id, first_id)
    if FRIEND_BLACK in (first_status, second_status):
        return StatusCode.StatusCode_FRIEND_BLACK
    if first_status != FRIEND_OK or second_status != FRIEND_OK:
        return StatusCode.StatusCode_FRIEND_NOT_EXIST
    return StatusCode.StatusCode_OK


def _load_history(raw):
    if not raw:
        return []
    history = pickle.loads(raw)
    if not isinstance(history, list):
        raise ValueError("private chat history must be a list")
    return history


def _private_fingerprint(message):
    # packet_id 是客户端请求标识；重试时发送时间会重新生成，不能参与指纹。
    return (
        str(message.get("text", "")),
        int(message.get("expression", 0) or 0),
    )


def send_private_message(sender_id, receiver_id, message, packet_id=0):
    """原子追加双方历史和接收者未读。

    返回 ``(status, stored_message, replayed)``。正数 ``packet_id`` 作为
    持久幂等键，重复/并发重试只返回首次结果，不重复历史、未读或通知。
    """
    with relation_transaction(sender_id, receiver_id):
        fingerprint = _private_fingerprint(message)
        operation_key = f"{receiver_id}:{packet_id}"
        if packet_id > 0:
            raw = db.get_kv(sender_id, _PRIVATE_OPERATION_NS, operation_key)
            if raw is not None:
                try:
                    operation = pickle.loads(raw)
                except (pickle.UnpicklingError, EOFError, TypeError, ValueError):
                    return StatusCode.StatusCode_BAD_REQ, None, False
                if (
                    not isinstance(operation, dict)
                    or operation.get("fingerprint") != fingerprint
                    or not isinstance(operation.get("message"), dict)
                ):
                    return StatusCode.StatusCode_BAD_REQ, None, False
                return StatusCode.StatusCode_OK, operation["message"], True

        status = private_chat_status(sender_id, receiver_id)
        if status != StatusCode.StatusCode_OK:
            return status, None, False

        key = pair_key(sender_id, receiver_id)
        history = _load_history(db.get_kv(0, _PRIVATE_HISTORY_NS, key, b""))
        stored = dict(message)
        stored.setdefault("send_time", int(time.time() * 1000))
        history.append(stored)
        limit = max(0, int(Config.CHAT_HISTORY_MAX))
        retained = history[-limit:] if limit else []
        db.set_kv(0, _PRIVATE_HISTORY_NS, key, pickle.dumps(retained))
        # 未读只属于接收者；发送者与其他玩家的计数不受影响。
        db.incr_kv(receiver_id, _PRIVATE_UNREAD_NS, str(sender_id), 1)
        if packet_id > 0:
            db.set_kv(
                sender_id,
                _PRIVATE_OPERATION_NS,
                operation_key,
                pickle.dumps({"fingerprint": fingerprint, "message": stored}),
            )
        return StatusCode.StatusCode_OK, stored, False


def read_private_history(reader_id, target_id):
    """返回 ``(status, history)``，读取时只清空读取者的未读。"""
    with relation_transaction(reader_id, target_id):
        status = private_chat_status(reader_id, target_id)
        if status != StatusCode.StatusCode_OK:
            return status, []
        key = pair_key(reader_id, target_id)
        history = list(_load_history(db.get_kv(0, _PRIVATE_HISTORY_NS, key, b"")))
        db.del_kv(reader_id, _PRIVATE_UNREAD_NS, str(target_id))
        return StatusCode.StatusCode_OK, history


def unread_count(player_id, peer_id):
    return int(db.get_kv(player_id, _PRIVATE_UNREAD_NS, str(peer_id), 0) or 0)


def private_chat_offline(player_id):
    """构造登录离线私聊条目，不消费未读。

    ``PlayerMainData`` 目前未接入本函数；保留该集成点供主智能体在获得
    修改其他 handler 的授权后替换空的 ``PrivateChatOfflineNotice``。
    """
    if player_id <= 0:
        return []
    with player_locks(player_id), db.transaction():
        result = []
        for peer_text, raw_count in db.get_kv_ns(player_id, _PRIVATE_UNREAD_NS).items():
            try:
                peer_id, count = int(peer_text), int(raw_count or 0)
            except (TypeError, ValueError):
                continue
            if count <= 0 or private_chat_status(player_id, peer_id) != StatusCode.StatusCode_OK:
                continue
            info = db.get_players_info(peer_id, "player_name,head,avatar_frame")
            if not info:
                continue
            name, head, avatar_frame = info
            result.append(
                {
                    "player_id": peer_id,
                    "name": name or "",
                    "head": head or 0,
                    "is_new_msg": True,
                    "avatar_frame": avatar_frame or 0,
                }
            )
        return sorted(result, key=lambda entry: entry["player_id"])


def send_friend_notice(actor_id, target_id, notice_type, sessions, self_session=None):
    """事务提交后通知当前操作方和目标方；每个接收方使用独立消息对象。"""
    if self_session is not None:
        notice = FriendHandleNotice(
            status=StatusCode.StatusCode_OK,
            type=notice_type,
            target_player_id=target_id,
        )
        self_session.send(MsgId.FriendHandleNotice, notice, 0)
    for session in sessions:
        if session.player_id != target_id:
            continue
        notice = FriendHandleNotice(
            status=StatusCode.StatusCode_OK,
            type=notice_type,
            target_player_id=actor_id,
        )
        session.send(MsgId.FriendHandleNotice, notice, 0)
