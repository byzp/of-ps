from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PlayerOfflineReq,
    PlayerOfflineRsp,
    PlayerOfflineReason,
    StatusCode,
)


@packet_handler(MsgId.PlayerOfflineReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerOfflineReq()
        req.ParseFromString(data)

        # 优雅登出: 只回 Rsp, 由客户端收到后自行断开连接, 服务端不主动 close socket
        rsp = PlayerOfflineRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.reason = PlayerOfflineReason.PlayerOfflineReason_NONE
        rsp.server_next_open_time = 0

        session.send(MsgId.PlayerOfflineRsp, rsp, packet_id)  # 玩家离线 1009 1010
