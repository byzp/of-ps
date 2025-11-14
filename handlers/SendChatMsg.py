from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import logging

import proto.OverField_pb2 as SendChatMsgReq_pb2
import proto.OverField_pb2 as SendChatMsgRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
from server.scene_data import up_chat_msg

logger = logging.getLogger(__name__)


@packet_handler(CmdId.SendChatMsgReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = SendChatMsgReq_pb2.SendChatMsgReq()
        req.ParseFromString(data)
        up_chat_msg(
            req.type,
            session.user_id,
            req.text,
            req.expression,
            session.scene_id,
            session.channel_id,
        )  # expression->res.chat.chat_emotion

        rsp = SendChatMsgRsp_pb2.SendChatMsgRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK  # TODO
        session.send(CmdId.SendChatMsgRsp, rsp, False, packet_id)  # 1933,1934 -> 1936
