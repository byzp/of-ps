from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import time

from config import Config

from proto.net_pb2 import DungeonRepeatEnterReq, DungeonRepeatEnterRsp, StatusCode

import utils.db as db
from utils.pb_create import make_SceneTeam, make_scene_treasure_boxes
from utils.dungeon_reward import dungeon_config, prerequisite_finished
from utils import treasure_box, dungeon_state


@packet_handler(MsgId.DungeonRepeatEnterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with dungeon_state.player_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = DungeonRepeatEnterReq()
        req.ParseFromString(data)

        rsp = DungeonRepeatEnterRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 重复进入当前副本(再来一次), 副本 id 沿用 session 中记录的当前副本
        dungeon_id = session.dungeon[0]
        cfg = dungeon_config(dungeon_id)
        if not cfg or not prerequisite_finished(session.player_id, cfg):
            rsp.status = StatusCode.StatusCode_DungeonUnlock
            session.send(MsgId.DungeonRepeatEnterRsp, rsp, packet_id)
            return
        char_ids = [req.char1, req.char2, req.char3]
        make_SceneTeam(session.player_id, char_ids, rsp.team, dungeon_id=dungeon_id)

        dg = rsp.dungeon_data
        if dungeon_id:
            blob = db.get_dungeon(session.player_id, dungeon_id)
            if blob:
                dg.ParseFromString(blob)
        dg.dungeon_id = dungeon_id
        dg.enter_times += 1
        dg.char1 = req.char1
        dg.char2 = req.char2
        dg.char3 = req.char3
        dg.last_enter_time = int(time.time())
        if dungeon_id:
            db.set_dungeon(session.player_id, dungeon_id, dg.SerializeToString())

        # 重置本次副本计时(参考 DungeonOperate 的计时逻辑)
        session.dungeon[1] = time.time()
        session.dungeon[2] = 0

        if cfg and cfg.get("new_mission_type") == Config.MATERIAL_DUNGEON_TYPE:
            treasure_box.reset_dungeon_boxes(session.player_id, dungeon_id)
        rsp.treasure_boxes.extend(
            make_scene_treasure_boxes(session, include_dynamic=False)
        )

        session.send(MsgId.DungeonRepeatEnterRsp, rsp, packet_id)  # 1331,1332
