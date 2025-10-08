import time
from datetime import datetime, timezone

from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId
import proto.OverField_pb2 as PlayerLoginRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2


@packet_handler(CmdId.PlayerLoginReq)
class PlayerLoginHandler(PacketHandler):
    def handle(self, session, data: bytes):
        rsp = PlayerLoginRsp_pb2.PlayerLoginRsp()
        rsp.analysis_account_id = "1234567"
        rsp.channel_id = 1
        rsp.client_log_server_token = "dG9rZW4="
        rsp.player_name = "abc"
        rsp.status = StatusCode_pb2.StatusCode_Ok
        rsp.register_time = 1743602341
        rsp.region_name = "cn_prod_main"
        rsp.server_time_ms = int(time.time() * 1000)
        rsp.server_time_zone = 28800#int(datetime.now(timezone.utc).astimezone().utcoffset().total_seconds())
        rsp.scene_id = 9999
        
        session.send(CmdId.PlayerLoginRsp, rsp)
