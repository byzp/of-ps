from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as OverField_pb2
import proto.OverField_pb2 as StatusCode_pb2
import time
import logging

logger = logging.getLogger(__name__)


@packet_handler(CmdId.PlayerPingReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = OverField_pb2.PlayerPingReq()
        req.ParseFromString(data)

        rsp = OverField_pb2.PlayerPingRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.client_time_ms = req.client_time_ms
        rsp.server_time_ms = int(time.time() * 1000)

        session.send(CmdId.PlayerPingRsp, rsp, True, packet_id)
