import pickle as _pickle

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PrivateChatMsgRecordReq,
    PrivateChatMsgRecordRsp,
    StatusCode,
)

import utils.db as db


@packet_handler(MsgId.PrivateChatMsgRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PrivateChatMsgRecordReq()
        req.ParseFromString(data)

        rsp = PrivateChatMsgRecordRsp()
        if not db.get_friend_info(session.player_id, req.target_player_id, "player_id")[
            0
        ]:
            rsp.status = StatusCode.StatusCode_FRIEND_NOT_EXIST
            session.send(MsgId.PrivateChatMsgRecordRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK

        a, b = sorted((session.player_id, req.target_player_id))
        raw = db.get_kv(0, "chat_private", f"{a}:{b}", b"")
        if raw:
            for m in reversed(_pickle.loads(raw)):
                if not isinstance(m, dict):
                    continue
                entry = rsp.msg_record.add()
                entry.player_id = m.get("player_id", 0)
                entry.head = m.get("head", 0)
                entry.badge = m.get("badge", 0)
                entry.name = m.get("name", "")
                entry.text = m.get("text", "")
                entry.expression = m.get("expression", 0)
                entry.send_time = m.get("send_time", 0)

        session.send(MsgId.PrivateChatMsgRecordRsp, rsp, packet_id)
