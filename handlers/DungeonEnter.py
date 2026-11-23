import time

from config import Config

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    DungeonEnterReq,
    DungeonEnterRsp,
    StatusCode,
    ServerSceneSyncDataNotice,
    SceneActionType,
    DungeonData,
)

import server.scene_data as scene_data
import utils.db as db
from utils import achieve_track as _at
from utils import treasure_box, dungeon_state
from utils.dungeon_reward import dungeon_config, prerequisite_finished
from utils.pb_create import make_SceneTeam, make_scene_treasure_boxes
from utils.res_loader import res


@packet_handler(MsgId.DungeonEnterReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with dungeon_state.player_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = DungeonEnterReq()
        req.ParseFromString(data)

        rsp = DungeonEnterRsp()
        cfg = dungeon_config(req.dungeon_id)
        if not cfg:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
            return
        if not prerequisite_finished(session.player_id, cfg):
            rsp.status = StatusCode.StatusCode_DungeonUnlock
            session.send(MsgId.DungeonEnterRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK
        char_ids = []
        char_ids.append(req.char1)
        char_ids.append(req.char2)
        char_ids.append(req.char3)
        make_SceneTeam(session.player_id, char_ids, rsp.team, dungeon_id=req.dungeon_id)
        # 读取玩家真实副本数据, 进入次数累加后回写
        # dungeon_id=0 时 get_dungeon 返回 dict 而非 bytes, 需跳过读写
        dg = DungeonData()
        if req.dungeon_id:
            dg_b = db.get_dungeon(session.player_id, req.dungeon_id)
            if dg_b:
                dg.ParseFromString(dg_b)
        dg.dungeon_id = req.dungeon_id
        dg.enter_times += 1
        dg.char1 = req.char1
        dg.char2 = req.char2
        dg.char3 = req.char3
        dg.last_enter_time = int(time.time())
        # 此处是离开大场景时的位置，出生点属于rsp.team，不要混用。
        dg.pos.CopyFrom(req.pos)
        dg.rot.CopyFrom(req.rot)
        if req.dungeon_id:
            db.set_dungeon(session.player_id, req.dungeon_id, dg.SerializeToString())
        rsp.dungeon_data.CopyFrom(dg)
        rsp.dungeon_data.pos.CopyFrom(req.pos)
        rsp.dungeon_data.rot.CopyFrom(req.rot)
        session.dungeon = [req.dungeon_id, 0, 0, -1]
        if cfg.get("new_mission_type") == Config.MATERIAL_DUNGEON_TYPE:
            treasure_box.reset_dungeon_boxes(session.player_id, req.dungeon_id)
        # DungeonEnterRsp 必须携带副本宝箱点位, 与通用场景通知共用状态构造。
        rsp.treasure_boxes.extend(
            make_scene_treasure_boxes(session, include_dynamic=False)
        )

        find = False
        for i in res.get("Abyss", {}).get("abyss_stage", {}).get("datas", []):
            for ii in i.get("abyss_stage_group_info", ()) or ():
                if ii["dungeon_i_d"] == req.dungeon_id:
                    if ii.get("is_double_team"):
                        session.dungeon[3] = 0
                    find = True
                    break
            if find:
                break
        session.send(MsgId.DungeonEnterRsp, rsp, packet_id)

        # 主线任务条件: 进入指定空间

        _at.report(session, "scene_enter", match=req.dungeon_id)

        # 向其他玩家广播离开事件
        notice = ServerSceneSyncDataNotice()
        notice.status = StatusCode.StatusCode_OK
        d = notice.data.add()
        d.player_id = session.player_id
        sd = d.server_data.add()
        sd.action_type = SceneActionType.SceneActionType_LEAVE
        scene_data.up_scene_action(session.scene_id, session.channel_id, notice)
