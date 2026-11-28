from config import Config
from server.scene_data import get_session as _gs

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import pickle
import time

from proto.net_pb2 import (
    ChatChannelType,
    ChatMsgNotice,
    SendChatMsgReq,
    SendChatMsgRsp,
    StatusCode,
)
from server.scene_data import up_chat_msg

import utils.db as db
from server import social
from utils.res_loader import res


def append_chat_history(msg_type: int, msg: dict, pair_key: str = ""):
    """原子追加频道历史；私聊发送应使用 ``social.send_private_message``。"""
    with db.transaction():
        if pair_key:
            raw = db.get_kv(0, "chat_private", pair_key, b"")
            history = pickle.loads(raw) if raw else []
            history.append(msg)
            limit = max(0, int(Config.CHAT_HISTORY_MAX))
            retained = history[-limit:] if limit else []
            db.set_kv(0, "chat_private", pair_key, pickle.dumps(retained))
            return
        if msg_type not in Config.PUBLIC_CHANNELS:
            return
        raw = db.get_kv(0, "chat_history", str(msg_type), b"")
        history = pickle.loads(raw) if raw else []
        history.append(msg)
        limit = max(0, int(Config.CHAT_HISTORY_MAX))
        retained = history[-limit:] if limit else []
        db.set_kv(0, "chat_history", str(msg_type), pickle.dumps(retained))


@packet_handler(MsgId.SendChatMsgReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SendChatMsgReq()
        req.ParseFromString(data)

        rate_limiter = getattr(session, "rate_limiter", None)
        if rate_limiter is not None and not rate_limiter.allow("chat"):
            session.send(
                MsgId.SendChatMsgRsp,
                SendChatMsgRsp(status=StatusCode.StatusCode_REQUESTS_TOO_FREQUENT),
                packet_id,
            )
            return

        # 聊天表情须在 Chat.chat_emotion 配置内(0=无); 校验须先于广播
        emotions = {
            item["i_d"]
            for item in res.get("Chat", {}).get("chat_emotion", {}).get("datas", [])
            if isinstance(item, dict)
        }
        if req.expression and emotions and req.expression not in emotions:
            session.send(
                MsgId.SendChatMsgRsp,
                SendChatMsgRsp(status=StatusCode.StatusCode_CFG_NOT_FOUND),
                packet_id,
            )
            return

        message = {
            "player_id": session.player_id,
            "head": session.avatar_id,
            "badge": session.badge_id,
            "name": session.player_name,
            "text": req.text,
            "expression": req.expression,
            "send_time": int(time.time() * 1000),
            "avatar_frame": int(
                db.get_players_info(session.player_id, "avatar_frame")[0] or 0
            ),
        }

        if req.type == ChatChannelType.ChatChannel_Private:
            status, stored, replayed = social.send_private_message(
                session.player_id, req.player_id, message, packet_id
            )
            if status != StatusCode.StatusCode_OK:
                session.send(MsgId.SendChatMsgRsp, SendChatMsgRsp(status=status), packet_id)
                return

            # 历史与未读提交后再通知；离线接收者保留未读供重启后读取。
            if not replayed:
                notice = ChatMsgNotice(
                    status=StatusCode.StatusCode_OK,
                    type=req.type,
                )
                notice.msg.player_id = stored["player_id"]
                notice.msg.head = stored["head"]
                notice.msg.badge = stored["badge"]
                notice.msg.name = stored["name"]
                notice.msg.text = stored["text"]
                notice.msg.expression = stored["expression"]
                notice.msg.send_time = stored["send_time"]
                notice.msg.avatar_frame = stored["avatar_frame"]
                for other in _gs():
                    if other.player_id == req.player_id:
                        other.send(MsgId.ChatMsgNotice, notice, 0)
        else:
            notice = ChatMsgNotice(
                status=StatusCode.StatusCode_OK,
                type=req.type,
            )
            notice.msg.player_id = message["player_id"]
            notice.msg.head = message["head"]
            notice.msg.badge = message["badge"]
            notice.msg.name = message["name"]
            notice.msg.text = message["text"]
            notice.msg.expression = message["expression"]
            notice.msg.send_time = message["send_time"]
            notice.msg.avatar_frame = message["avatar_frame"]
            up_chat_msg(
                session.chat_channel_id,
                session.scene_id,
                session.channel_id,
                notice,
            )
            with social.player_locks(session.player_id):
                append_chat_history(req.type, message)

        session.send(
            MsgId.SendChatMsgRsp,
            SendChatMsgRsp(status=StatusCode.StatusCode_OK, text=req.text),
            packet_id,
        )
