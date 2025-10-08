from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as OverField_pb2
import proto.OverField_pb2 as StatusCode_pb2
import time
import logging

logger = logging.getLogger(__name__)

@packet_handler(CmdId.PlayerPingReq)
class PlayerPingHandler(PacketHandler):
    """
      request:  PlayerPingReq { int64 client_time_ms }
      response: PlayerPingRsp { StatusCode status; int64 client_time_ms; int64 server_time_ms }
    """
    def handle(self, session, data: bytes):
        try:
            req = OverField_pb2.PlayerPingReq()
            req.ParseFromString(data)

            rsp = OverField_pb2.PlayerPingRsp()
            rsp.client_time_ms = req.client_time_ms
            rsp.server_time_ms = int(time.time() * 1000)

            rsp.status = StatusCode_pb2.StatusCode_Ok

            session.send(CmdId.PlayerPingRsp, rsp)

        except Exception as e:
            logger.exception("failed to handle PlayerPingReq")
            print(str(e))