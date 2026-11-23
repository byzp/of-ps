from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import UnfreezePlayerActionReq, UnfreezePlayerActionRsp, StatusCode


@packet_handler(MsgId.UnfreezePlayerActionReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UnfreezePlayerActionReq()
        req.ParseFromString(data)

        rsp = UnfreezePlayerActionRsp()
        rsp.status = StatusCode.StatusCode_OK

        session.send(
            MsgId.UnfreezePlayerActionRsp, rsp, packet_id
        )  # 解冻玩家操作 2535 2536
