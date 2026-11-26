from utils import achieve_track, dungeon_state

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import DungeonViewReq, DungeonViewRsp, StatusCode
import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.DungeonViewReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with dungeon_state.player_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = DungeonViewReq()
        req.ParseFromString(data)

        rsp = DungeonViewRsp()
        if not any(
            isinstance(r, dict) and r.get("i_d") == req.dungeon_id
            for r in res.get("Dungeon", {}).get("dungeon", {}).get("datas", ())
        ):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonViewRsp, rsp, packet_id)
            return
        rsp.status = StatusCode.StatusCode_OK

        # 副本进度回显(无记录则仅回 dungeon_id)
        blob = db.get_dungeon(session.player_id, req.dungeon_id)
        if blob:
            rsp.dungeon_data.ParseFromString(blob)
            if not rsp.dungeon_data.dungeon_id:
                rsp.dungeon_data.dungeon_id = req.dungeon_id
        else:
            rsp.dungeon_data.dungeon_id = req.dungeon_id

        # 副本任务进度(Dungeon.dungeon_quest 条件 → Achieve 进度)

        # dungeon 行经 dengeon_quest_i_d指向任务组号
        # (dungeon_quest.i_d 为组号 101/110/212 型, 与副本 id 不同空间)
        quest_group_id = next(
            (
                e.get("dengeon_quest_i_d")
                for e in res.get("Dungeon", {}).get("dungeon", {}).get("datas", ())
                if isinstance(e, dict) and e.get("i_d") == req.dungeon_id
            ),
            None,
        )
        for row in res.get("Dungeon", {}).get("dungeon_quest", {}).get("datas", []):
            if not quest_group_id or row.get("i_d") != quest_group_id:
                continue
            for info in row.get("dungeon_quest_group_info", ()) or ():
                cid = info.get("achieve_condition_i_d")
                if not cid:
                    continue
                task = rsp.task_data_lst.add()
                task.achieve_id = cid
                task.count = achieve_track.progress(session.player_id, int(cid))
                if not task.count:
                    del rsp.task_data_lst[-1]

        session.send(MsgId.DungeonViewRsp, rsp, packet_id)
