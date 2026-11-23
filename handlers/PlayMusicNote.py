import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    PlayMusicNoteReq,
    PlayMusicNoteRsp,
    ServerSceneSyncDataNotice,
    StatusCode,
    SceneActionType,
)
import utils.db as db
from utils.res_loader import res
from server.scene_data import up_scene_action


@packet_handler(MsgId.PlayMusicNoteReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayMusicNoteReq()
        req.ParseFromString(data)

        start_time = int(time.time() * 1000)

        rsp = PlayMusicNoteRsp()

        # 音符须在 MusicNote.music_note 配置内
        _notes = {
            m["i_d"]
            for m in res.get("MusicNote", {}).get("music_note", {}).get("datas", [])
            if isinstance(m, dict)
        }
        if _notes and req.music_note_id and req.music_note_id not in _notes:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.PlayMusicNoteRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        rsp.player_id = session.player_id
        rsp.music_note_id = req.music_note_id
        rsp.start_time = start_time
        session.send(MsgId.PlayMusicNoteRsp, rsp, packet_id)  # 2673,2674

        # 同步演奏状态到场景玩家数据并广播(参考 ChangeMusicalItem)
        if req.music_note_id:
            session.scene_player.playing_music_note.music_note_id = req.music_note_id
            session.scene_player.playing_music_note.start_time = start_time
        else:
            session.scene_player.ClearField("playing_music_note")
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        data_entry = notice.data.add()
        data_entry.player_id = session.player_id
        server_data_entry = data_entry.server_data.add()
        server_data_entry.action_type = (
            SceneActionType.SceneActionType_UPDATE_MUSICAL_ITEM
        )
        server_data_entry.player.CopyFrom(session.scene_player)
        up_scene_action(session.scene_id, session.channel_id, notice)
