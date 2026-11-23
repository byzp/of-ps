from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    AccountNameBindingCancelReq,
    AccountNameBindingCancelRsp,
    StatusCode,
)


@packet_handler(MsgId.AccountNameBindingCancelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AccountNameBindingCancelReq()
        req.ParseFromString(data)

        rsp = AccountNameBindingCancelRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.player_id = session.player_id

        session.send(
            MsgId.AccountNameBindingCancelRsp, rsp, packet_id
        )  # 取消账号名绑定 2263 2264
