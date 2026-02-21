from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import PlayerPingReq, PlayerPingRsp, StatusCode
import time
import logging

logger = logging.getLogger(__name__)


@packet_handler(MsgId.PlayerPingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerPingReq()
        req.ParseFromString(data)

        rsp = PlayerPingRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.client_time_ms = req.client_time_ms
        rsp.server_time_ms = int(time.time() * 1000)

        session.send(MsgId.PlayerPingRsp, rsp, packet_id)
