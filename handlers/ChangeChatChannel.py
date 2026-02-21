from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangeChatChannelReq, ChangeChatChannelRsp, StatusCode


@packet_handler(MsgId.ChangeChatChannelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeChatChannelReq()
        req.ParseFromString(data)

        rsp = ChangeChatChannelRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.chat_channel_id = req.channel_id
        rsp.chat_channel_id = req.channel_id

        session.send(MsgId.ChangeChatChannelRsp, rsp, packet_id)  # 1930,1931
