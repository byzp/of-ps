from utils import achieve_track, dungeon_state

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import time

from proto.net_pb2 import DungeonOperateReq, DungeonOperateRsp, StatusCode, DungeonData

import utils.db as db
from utils.res_loader import res


def _star_timers(dungeon_id):
    """Dungeon.json dungeon.star_timer1/2/3(秒): 1/2/3 星的用时上限"""
    for e in res.get("Dungeon", {}).get("dungeon", {}).get("datas", ()):
        if e.get("i_d") == dungeon_id:
            t1 = e.get("star_timer1", 0)
            if t1:
                return (
                    t1,
                    e.get("star_timer2", t1),
                    e.get("star_timer3", t1),
                )
            break
    return None


@packet_handler(MsgId.DungeonOperateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with dungeon_state.player_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = DungeonOperateReq()
        req.ParseFromString(data)

        rsp = DungeonOperateRsp()
        rsp.status = StatusCode.StatusCode_OK
        if req.operate_type == DungeonOperateReq.DungeonOperateType.START:
            session.dungeon[1] = time.time()
        if req.operate_type == DungeonOperateReq.DungeonOperateType.END:
            session.dungeon[2] += int((time.time() - session.dungeon[1]) * 1000)
            rsp.consume_time = session.dungeon[2]
            if session.dungeon[3] == 0:
                session.dungeon[1] = time.time()
            else:
                # 星级按 Dungeon.json star_timer1/2/3 判定(毫秒比较)
                timers = _star_timers(session.dungeon[0])
                t1, t2, t3 = timers if timers else (0, 0, 0)
                if rsp.consume_time < t1 * 1000:
                    rsp.star = 1
                if rsp.consume_time < t2 * 1000:
                    rsp.star = 2
                if rsp.consume_time < t3 * 1000:
                    rsp.star = 3
                if not session.dungeon[0]:
                    rsp.status = StatusCode.StatusCode_PlayerNotInDungeon
                    session.send(MsgId.DungeonOperateRsp, rsp, packet_id)
                    return
                dg = DungeonData()
                dg.ParseFromString(
                    db.get_dungeon(session.player_id, session.dungeon[0])
                )
                if rsp.consume_time < dg.last_finish_time or dg.last_finish_time == 0:
                    dg.last_finish_time = rsp.consume_time
                db.set_dungeon(session.player_id, dg.dungeon_id, dg.SerializeToString())

        session.send(MsgId.DungeonOperateRsp, rsp, packet_id)
        if req.operate_type == DungeonOperateReq.DungeonOperateType.END and rsp.star:

            # 评价星数是累计型成就，按本次结算实际星数增加。
            achieve_track.report(session, "dungeon_rating", amount=rsp.star)
