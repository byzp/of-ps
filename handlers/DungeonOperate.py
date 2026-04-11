from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import time

from proto.net_pb2 import DungeonOperateReq, DungeonOperateRsp, StatusCode, DungeonData

import utils.db as db


@packet_handler(MsgId.DungeonOperateReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
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
                if rsp.consume_time < 200 * 1000:
                    rsp.star = 1
                if rsp.consume_time < 150 * 1000:
                    rsp.star = 2
                if rsp.consume_time < 100 * 1000:
                    rsp.star = 3
                dg = DungeonData()
                dg.ParseFromString(
                    db.get_dungeon(session.player_id, session.dungeon[0])
                )
                if rsp.consume_time < dg.last_finish_time or dg.last_finish_time == 0:
                    dg.last_finish_time = rsp.consume_time
                db.set_dungeon(session.player_id, dg.dungeon_id, dg.SerializeToString())

        session.send(MsgId.DungeonOperateRsp, rsp, packet_id)
