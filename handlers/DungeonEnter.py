import time
import uuid

from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import (
    Character,
    DungeonData,
    DungeonEnterReq,
    DungeonEnterRsp,
    SceneActionType,
    ServerSceneSyncDataNotice,
    StatusCode,
)
import server.scene_data as scene_data
import utils.db as db
from utils import achieve_track as _at
from utils import treasure_box
from utils.dungeon_reward import dungeon_config, prerequisite_finished
from utils.pb_create import make_SceneTeam, make_scene_treasure_boxes
from utils.res_loader import res


@packet_handler(MsgId.DungeonEnterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonEnterReq()
        req.ParseFromString(data)
        rsp = DungeonEnterRsp()
        cfg = dungeon_config(req.dungeon_id)
        if not cfg:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
            return
        if session.dungeon[0]:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
            return
        if not prerequisite_finished(session.player_id, cfg):
            rsp.status = StatusCode.StatusCode_DungeonUnlock
            session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
            return
        level = db.get_players_info(session.player_id, "level")[0] or 1
        if level < int(cfg.get("need_player_level", 1)):
            rsp.status = StatusCode.StatusCode_Lv_Not_Enough
            session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
            return
        char_ids = list(dict.fromkeys(value for value in (req.char1, req.char2, req.char3) if value))
        if not char_ids or len(char_ids) > int(cfg.get("use_character_max_number", 3)):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
            return
        owned = set()
        for blob in db.get_characters(session.player_id):
            character = Character()
            character.ParseFromString(blob)
            owned.add(character.character_id)
        if any(character_id not in owned for character_id in char_ids):
            rsp.status = StatusCode.StatusCode_CharNotExist
            session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
            return

        make_SceneTeam(session.player_id, char_ids, rsp.team, dungeon_id=req.dungeon_id)
        dg = DungeonData()
        if req.dungeon_id:
            blob = db.get_dungeon(session.player_id, req.dungeon_id)
            if blob:
                dg.ParseFromString(blob)
        dg.dungeon_id = req.dungeon_id
        dg.enter_times += 1
        dg.char1 = req.char1
        dg.char2 = req.char2
        dg.char3 = req.char3
        dg.last_enter_time = int(time.time())
        dg.pos.CopyFrom(req.pos)
        dg.rot.CopyFrom(req.rot)
        if req.dungeon_id:
            db.set_dungeon(session.player_id, req.dungeon_id, dg.SerializeToString())
        rsp.dungeon_data.CopyFrom(dg)
        rsp.dungeon_data.pos.CopyFrom(req.pos)
        rsp.dungeon_data.rot.CopyFrom(req.rot)
        session.dungeon = [req.dungeon_id, time.time(), 0, -1]
        session.dungeon_token = uuid.uuid4().hex
        if cfg.get("new_mission_type") == Config.MATERIAL_DUNGEON_TYPE:
            treasure_box.reset_dungeon_boxes(session.player_id, req.dungeon_id)
        rsp.treasure_boxes.extend(make_scene_treasure_boxes(session, include_dynamic=False))

        double_team = False
        for stage in res.get("Abyss", {}).get("abyss_stage", {}).get("datas", []):
            for info in stage.get("abyss_stage_group_info", ()) or ():
                if info["dungeon_i_d"] == req.dungeon_id and info.get("is_double_team"):
                    session.dungeon[3] = 0
                    double_team = True
                    break
            if double_team:
                break
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
        _at.report(session, "scene_enter", match=req.dungeon_id)
        notice = ServerSceneSyncDataNotice(status=StatusCode.StatusCode_OK)
        event = notice.data.add()
        event.player_id = session.player_id
        event.server_data.add().action_type = SceneActionType.SceneActionType_LEAVE
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)
