from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as ChangeChatChannelReq_pb2
import proto.OverField_pb2 as ChangeChatChannelRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(CmdId.ChangeChatChannelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeChatChannelReq_pb2.ChangeChatChannelReq()
        req.ParseFromString(data)

        rsp = ChangeChatChannelRsp_pb2.ChangeChatChannelRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        session.chat_channel_id = req.channel_id
        rsp.chat_channel_id = req.channel_id

        session.send(CmdId.ChangeChatChannelRsp, rsp, packet_id)  # 1930,1931
