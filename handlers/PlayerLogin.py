import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import PlayerLoginReq, PlayerLoginRsp, StatusCode
import utils.db as db
import server.scene_data as scene_data
import utils.pb_create as pb_create
from network.remote_link import sync_player


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
        rsp.region_name = db.get_players_info(player_id, "region_name")
        rsp.register_time = db.get_players_info(player_id, "register_time")
        rsp.analysis_account_id = db.get_analysis_account_id(player_id)
        rsp.server_time_zone = db.get_players_info(
            player_id, "server_time_zone"
        )  # int(datetime.now(timezone.utc).astimezone().utcoffset().total_seconds())
        rsp.player_name = db.get_players_info(player_id, "player_name")
        rsp.client_log_server_token = db.get_players_info(
            player_id, "client_log_server_token"
        )
        session.scene_id = scene_data.get_scene_id(player_id)
        session.channel_id = scene_data.get_channel_id(player_id)
        rsp.scene_id = session.scene_id
        rsp.channel_id = session.channel_id

        pb_create.make_ScenePlayer(session)

        session.send(MsgId.PlayerLoginRsp, rsp, packet_id)  # 1003,1004

        sync_player(session)
