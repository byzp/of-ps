from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    Achieve,
    ChangeWorldLevelReq,
    ChangeWorldLevelRsp,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.ChangeWorldLevelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ChangeWorldLevelReq()
        req.ParseFromString(data)

        rsp = ChangeWorldLevelRsp()

        # 世界等级合法区间对 Level.world_level 表
        max_wl = max(d["i_d"] for d in res["Level"]["world_level"]["datas"])

        if req.world_level <= 0 or req.world_level > max_wl:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            row = db.get_players_info(session.player_id, "world_level")
            rsp.world_level = row[0] if row else 1
        else:
            row = db.get_players_info(session.player_id, "world_level")
            cur_wl = row[0] if row else 1
            if cur_wl == req.world_level:
                rsp.status = StatusCode.StatusCode_WORLD_LEVEL_NOW_IN
                rsp.world_level = cur_wl
                session.send(MsgId.ChangeWorldLevelRsp, rsp, packet_id)
                return
            # 校验目标世界等级解锁条件:
            unlocked = True
            for wl in res["Level"]["world_level"]["datas"]:
                if wl.get("i_d") == req.world_level:
                    need_level = wl.get("level", 0)
                    row_lv = db.get_players_info(session.player_id, "level")
                    cur_lv = row_lv[0] if row_lv else 1
                    if need_level and cur_lv < need_level:
                        unlocked = False
                    for info in wl.get("world_level_info", ()) or ():
                        ach_id = info.get("achieve_i_d")
                        if not ach_id:
                            continue
                        blob = db.get_achieve(session.player_id, ach_id)
                        if not blob:
                            unlocked = False
                            break
                        a = Achieve()
                        a.ParseFromString(blob)
                        if a.count <= 0:
                            unlocked = False
                            break
                    break
            if not unlocked:
                rsp.status = StatusCode.StatusCode_FAIL
                row = db.get_players_info(session.player_id, "world_level")
                rsp.world_level = row[0] if row else 1
            else:
                rsp.status = StatusCode.StatusCode_OK
                db.set_players_info(session.player_id, "world_level", req.world_level)
                rsp.world_level = req.world_level

        session.send(
            MsgId.ChangeWorldLevelRsp, rsp, packet_id
        )  # 切换世界等级 1527 1528
