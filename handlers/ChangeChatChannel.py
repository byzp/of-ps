from proto.net_pb2 import ChangeChatChannelNotice

from server import scene_data as _sd

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ChangeChatChannelReq, ChangeChatChannelRsp, StatusCode
import utils.db as db


@packet_handler(MsgId.ChangeChatChannelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeChatChannelReq()
        req.ParseFromString(data)

        rsp = ChangeChatChannelRsp()
        rsp.status = StatusCode.StatusCode_OK
        session.chat_channel_id = req.channel_id
        rsp.channel_id = req.channel_id

        session.send(MsgId.ChangeChatChannelRsp, rsp, packet_id)  # 1930,1931

        # 频道切换广播

        _n = ChangeChatChannelNotice()
        _n.status = StatusCode.StatusCode_OK
        _n.channel_id = req.channel_id
        for _s in _sd.get_session():
            if _s.scene_id == session.scene_id and _s.channel_id == session.channel_id:
                _s.send(MsgId.ChangeChatChannelNotice, _n, 0)
