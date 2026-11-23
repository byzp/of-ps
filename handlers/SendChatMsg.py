from config import Config
from server.scene_data import get_session as _gs

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import time

from proto.net_pb2 import (
    ChatChannelType,
    ChatMsgNotice,
    SendChatMsgReq,
    SendChatMsgRsp,
    StatusCode,
)
from server.scene_data import up_chat_msg

import pickle

import utils.db as db
from utils.res_loader import res


def append_chat_history(msg_type: int, msg: dict, pair_key: str = ""):
    if pair_key:
        # 私聊: 按双方 id 排序成对存储, 每对保留 50 条
        raw = db.get_kv(0, "chat_private", pair_key, b"")
        history = pickle.loads(raw) if raw else []
        history.append(msg)
        db.set_kv(
            0,
            "chat_private",
            pair_key,
            pickle.dumps(history[-Config.CHAT_HISTORY_MAX :]),
        )
        return
    if msg_type not in Config.PUBLIC_CHANNELS:
        return
    raw = db.get_kv(0, "chat_history", str(msg_type), b"")
    history = pickle.loads(raw) if raw else []
    history.append(msg)
    db.set_kv(
        0,
        "chat_history",
        str(msg_type),
        pickle.dumps(history[-Config.CHAT_HISTORY_MAX :]),
    )


@packet_handler(MsgId.SendChatMsgReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SendChatMsgReq()
        req.ParseFromString(data)

        rsp = SendChatMsgRsp()

        # 聊天表情须在 Chat.chat_emotion 配置内(0=无); 校验须先于广播
        _emo = {
            c["i_d"]
            for c in res.get("Chat", {}).get("chat_emotion", {}).get("datas", [])
            if isinstance(c, dict)
        }
        if req.expression and _emo and req.expression not in _emo:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.SendChatMsgRsp, rsp, packet_id)
            return

        tmp = ChatMsgNotice()
        tmp.status = StatusCode.StatusCode_OK
        tmp.type = req.type
        tmp.msg.player_id = session.player_id
        tmp.msg.head = session.avatar_id
        tmp.msg.badge = session.badge_id
        tmp.msg.name = session.player_name
        tmp.msg.text = req.text
        tmp.msg.expression = req.expression
        tmp.msg.send_time = int(time.time() * 1000)
        tmp.msg.avatar_frame = int(
            db.get_players_info(session.player_id, "avatar_frame")[0] or 0
        )
        if req.type == ChatChannelType.ChatChannel_Private and req.player_id:
            for other in _gs():
                if other.player_id == req.player_id:
                    other.send(MsgId.ChatMsgNotice, tmp, 0)
                    break
        else:
            up_chat_msg(
                session.chat_channel_id, session.scene_id, session.channel_id, tmp
            )  # expression->res.chat.chat_emotion
        pair_key = ""
        if req.type == ChatChannelType.ChatChannel_Private and req.player_id:
            a, b = sorted((session.player_id, req.player_id))
            pair_key = f"{a}:{b}"
        append_chat_history(
            req.type,
            {
                "player_id": tmp.msg.player_id,
                "head": tmp.msg.head,
                "badge": tmp.msg.badge,
                "name": tmp.msg.name,
                "text": tmp.msg.text,
                "expression": tmp.msg.expression,
                "send_time": tmp.msg.send_time,
            },
            pair_key,
        )

        rsp = SendChatMsgRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.text = req.text
        session.send(MsgId.SendChatMsgRsp, rsp, packet_id)  # 1933,1934 -> 1936
