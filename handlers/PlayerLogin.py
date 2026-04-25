import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config

from proto.net_pb2 import PlayerLoginReq, PlayerLoginRsp, StatusCode
import utils.db as db
import server.scene_data as scene_data


@packet_handler(MsgId.PlayerLoginReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerLoginReq()
        req.ParseFromString(data)

        rsp = PlayerLoginRsp()

        player_id = session.player_id
        if req.is_reconnect == True:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.PlayerLoginRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        rsp.server_time_ms = int(time.time() * 1000)
        (
            rsp.region_name,
            rsp.register_time,
            rsp.server_time_zone,
            rsp.player_name,
            rsp.client_log_server_token,
        ) = db.get_players_info(
            player_id,
            "region_name,register_time,server_time_zone,player_name,client_log_server_token",
        )
        rsp.analysis_account_id = db.get_analysis_account_id(player_id)
        # rsp.server_time_zone # int(datetime.now(timezone.utc).astimezone().utcoffset().total_seconds())
        if rsp.player_name == "" and not Config.SKIP_QUESTS:
            session.scene_id = 100  # 新玩家
        else:
            session.scene_id = scene_data.get_scene_id(player_id)
        session.channel_id = scene_data.get_channel_id(player_id)
        rsp.scene_id = session.scene_id
        rsp.channel_id = session.channel_id
        session.send(MsgId.PlayerLoginRsp, rsp, packet_id)  # 1003,1004
