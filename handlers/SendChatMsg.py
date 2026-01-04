from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging
import time

import proto.OverField_pb2 as SendChatMsgReq_pb2
import proto.OverField_pb2 as SendChatMsgRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as ChatMsgNotice
from server.scene_data import up_chat_msg

logger = logging.getLogger(__name__)


@packet_handler(MsgId.SendChatMsgReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SendChatMsgReq_pb2.SendChatMsgReq()
        req.ParseFromString(data)

        tmp = ChatMsgNotice.ChatMsgNotice()
        tmp.status = StatusCode_pb2.StatusCode_OK
        tmp.type = req.type
        tmp.msg.player_id = session.player_id
        tmp.msg.head = session.avatar_id
        tmp.msg.badge = session.badge_id
        tmp.msg.name = session.player_name
        tmp.msg.text = req.text
        tmp.msg.expression = req.expression
        tmp.msg.send_time = int(time.time() * 1000)
        up_chat_msg(
            session.chat_channel_id, session.scene_id, session.channel_id, tmp
        )  # expression->res.chat.chat_emotion

        rsp = SendChatMsgRsp_pb2.SendChatMsgRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK  # TODO
        session.send(MsgId.SendChatMsgRsp, rsp, packet_id)  # 1933,1934 -> 1936
