import time
from datetime import datetime, timezone

from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as PlayerLoginReq_pb2
import proto.OverField_pb2 as PlayerLoginRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db


@packet_handler(CmdId.PlayerLoginReq)
class PlayerLoginHandler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerLoginReq_pb2.PlayerLoginReq()
        req.ParseFromString(data)

        rsp = PlayerLoginRsp_pb2.PlayerLoginRsp()

        user_id = session.user_id
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.server_time_ms = int(time.time() * 1000)
        rsp.region_name = db.get_region_name(user_id)
        rsp.register_time = db.get_register_time(user_id)
        rsp.analysis_account_id = db.get_analysis_account_id(user_id)
        rsp.server_time_zone = db.get_server_time_zone(
            user_id
        )  # int(datetime.now(timezone.utc).astimezone().utcoffset().total_seconds())
        rsp.player_name = db.get_player_name(user_id)
        rsp.client_log_server_token = db.get_client_log_server_token(user_id)
        rsp.scene_id = 9999
        rsp.channel_id = 1

        session.send(CmdId.PlayerLoginRsp, rsp, True, packet_id)  # 1003,1004
