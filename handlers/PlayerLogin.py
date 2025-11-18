import time
from datetime import datetime, timezone

from network.packet_handler import PacketHandler, packet_handler
from network.cmd_id import CmdId

import proto.OverField_pb2 as PlayerLoginReq_pb2
import proto.OverField_pb2 as PlayerLoginRsp_pb2
import proto.OverField_pb2 as StatusCode_pb2
import proto.OverField_pb2 as pb
import utils.db as db
import server.scene_data as scene_data


@packet_handler(CmdId.PlayerLoginReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerLoginReq_pb2.PlayerLoginReq()
        req.ParseFromString(data)

        rsp = PlayerLoginRsp_pb2.PlayerLoginRsp()

        player_id = session.player_id
        if req.is_reconnect == True:
            rsp.status = StatusCode_pb2.StatusCode_FAIL
            session.send(CmdId.PlayerLoginRsp, rsp, True, packet_id)
            return
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.server_time_ms = int(time.time() * 1000)
        rsp.region_name = db.get_region_name(player_id)
        rsp.register_time = db.get_register_time(player_id)
        rsp.analysis_account_id = db.get_analysis_account_id(player_id)
        rsp.server_time_zone = db.get_server_time_zone(
            player_id
        )  # int(datetime.now(timezone.utc).astimezone().utcoffset().total_seconds())
        rsp.player_name = db.get_player_name(player_id)
        rsp.client_log_server_token = db.get_client_log_server_token(player_id)
        session.scene_id = scene_data.get_scene_id(player_id)
        session.channel_id = scene_data.get_channel_id(player_id)
        rsp.scene_id = session.scene_id
        rsp.channel_id = session.channel_id

        # 构造ScenePlayer
        player = session.scene_player
        player.player_id = session.player_id
        player.player_name = session.player_name
        char_ids = db.get_team_char_id(player_id)
        char_1 = player.team.char_1
        char_1.char_id = char_ids[0]
        char_1.outfit_preset.hide_info.CopyFrom(pb.OutfitHideInfo())

        for chr in db.get_characters(player_id):
            if chr["character_id"] == char_1.char_id:
                for k, v in chr["character_appearance"].items():
                    setattr(char_1.character_appearance, k, v)
                char_1.char_lv = chr["level"]
                char_1.char_star = chr["star"]
                char_1.char_break_lv = chr["max_level"]
        # char_1.pos.CopyFrom(pb.Vector3())
        # char_1.rot.CopyFrom(pb.Vector3())
        char_1.pos.x = 2394
        char_1.pos.y = 908
        char_1.rot.CopyFrom(pb.Vector3())

        session.send(CmdId.PlayerLoginRsp, rsp, True, packet_id)  # 1003,1004
