from utils import achieve_track, dungeon_state

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import DungeonFinishReq, DungeonFinishRsp, StatusCode
import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.DungeonFinishReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with dungeon_state.player_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = DungeonFinishReq()
        req.ParseFromString(data)

        rsp = DungeonFinishRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.scene_id = session.scene_id
        if not session.dungeon[0]:
            rsp.status = StatusCode.StatusCode_PlayerNotInDungeon
            session.send(MsgId.DungeonFinishRsp, rsp, packet_id)
            return
        dg = rsp.dungeon_data
        dg.CopyFrom(dungeon_state.load(session.player_id, session.dungeon[0]))
        first = db.try_claim(
            session.player_id, "dungeon_finish_run", f"{dg.dungeon_id}:{dg.enter_times}"
        )
        # 探索度在首次发现(进入)时已计, 通关不重复计数
        if first:
            dg.finish_times += 1

        dungeon_cfg = next(
            (
                row
                for row in res.get("Dungeon", {}).get("dungeon", {}).get("datas", ())
                if isinstance(row, dict) and row.get("i_d") == dg.dungeon_id
            ),
            None,
        )
        mission_type = dungeon_cfg.get("new_mission_type") if dungeon_cfg else None

        with achieve_track.batch(session):
            # 副本条件按 Dungeon.new_mission_type 分类；普通战斗本计116，
            # 资源获取本计117，指定副本条件仍按 dungeon_id 精确匹配。
            if first:
                achieve_track.report(
                    session,
                    "dungeon_finish",
                    match=dg.dungeon_id,
                    mission_type=mission_type,
                )
                dungeon_state.save(session, dg)
            session.send(MsgId.DungeonFinishRsp, rsp, packet_id)
