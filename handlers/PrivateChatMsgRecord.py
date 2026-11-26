from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PrivateChatMsgRecordReq,
    PrivateChatMsgRecordRsp,
    StatusCode,
)

from server import social


@packet_handler(MsgId.PrivateChatMsgRecordReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PrivateChatMsgRecordReq()
        req.ParseFromString(data)

        status, history = social.read_private_history(
            session.player_id, req.target_player_id
        )
        rsp = PrivateChatMsgRecordRsp(status=status)
        if status == StatusCode.StatusCode_OK:
            for message in reversed(history):
                if not isinstance(message, dict):
                    continue
                entry = rsp.msg_record.add()
                entry.player_id = message.get("player_id", 0)
                entry.head = message.get("head", 0)
                entry.badge = message.get("badge", 0)
                entry.name = message.get("name", "")
                entry.text = message.get("text", "")
                entry.expression = message.get("expression", 0)
                entry.send_time = message.get("send_time", 0)
                entry.avatar_frame = message.get("avatar_frame", 0)

        session.send(MsgId.PrivateChatMsgRecordRsp, rsp, packet_id)
