import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from config import Config

from proto.net_pb2 import PlayerLoginReq, PlayerLoginRsp, StatusCode
import utils.db as db
import server.scene_data as scene_data
from utils import achieve_track


@packet_handler(MsgId.PlayerLoginReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerLoginReq()
        req.ParseFromString(data)

        rsp = PlayerLoginRsp()
        if req.is_reconnect and session.logged_in:
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.PlayerLoginRsp, rsp, packet_id)
            return

        player_id = session.player_id
        rsp.status = StatusCode.StatusCode_OK
        rsp.server_time_ms = int(time.time() * 1000)
        rsp.is_reconnect = req.is_reconnect
        restored_location = False
        # 成就: 每日登录82(每自然日一次) + 队长等级36族同步
        # , 合并为一个动作帧
        with achieve_track.batch(session, notify=False):
            achieve_track.daily_login(session)
            achieve_track.captain_level(
                session, int(db.get_players_info(player_id, "level")[0] or 1)
            )
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
        # rsp.server_time_zone # int(datetime.now(timezone.utc).astimezone().utcoffset().total_seconds())。。
        if not Config.SKIP_QUESTS and (
            not rsp.player_name
            or db.get_kv(player_id, "profile", "tutorial_pending", 0)
        ):
            session.scene_id = 100  # 新玩家
            session.channel_id = scene_data.get_channel_id(player_id)
        else:
            restored_location = scene_data.restore_session_location(session)
            if not restored_location:
                session.scene_id = scene_data.get_scene_id(player_id)
                session.channel_id = scene_data.get_channel_id(player_id)
        rsp.reconnect_success = bool(req.is_reconnect and restored_location)
        rsp.scene_id = session.scene_id
        rsp.channel_id = session.channel_id
        session.send(MsgId.PlayerLoginRsp, rsp, packet_id)  # 1003,1004
