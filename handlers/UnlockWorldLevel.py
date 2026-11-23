from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import UnlockWorldLevelReq, UnlockWorldLevelRsp, Achieve, StatusCode

import utils.db as db
from utils.res_loader import res


@packet_handler(MsgId.UnlockWorldLevelReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = UnlockWorldLevelReq()
        req.ParseFromString(data)

        rsp = UnlockWorldLevelRsp()
        rsp.status = StatusCode.StatusCode_OK

        row = db.get_players_info(session.player_id, "world_level")
        current = row[0] if row else 1

        # 世界等级合法区间与解锁条件对 Level.world_level 表(当前版本 1-6)
        max_wl = 6
        target_cfg = None
        _tab = (
            res["Level"]["world_level"]["datas"]
            if isinstance(res.get("Level"), dict)
            and isinstance(res["Level"].get("world_level"), dict)
            else None
        )
        _tab = _tab if isinstance(_tab, (list, tuple)) else None
        if _tab:
            _ids = [d["i_d"] for d in _tab if isinstance(d, dict) and "i_d" in d]
            max_wl = max(_ids) if _ids else 6
            for d in _tab:
                if isinstance(d, dict) and d.get("i_d") == req.world_level:
                    target_cfg = d
                    break
        if req.world_level < 1 or req.world_level > max_wl:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            rsp.world_level = current
            session.send(MsgId.UnlockWorldLevelRsp, rsp, packet_id)
            return

        # 解锁条件校验: world_level_info 的 achieve_i_d 全部达成
        if req.world_level > current and target_cfg is not None:
            need = {}
            _ach = (
                res["Achieve"]["achieve"]["datas"]
                if isinstance(res.get("Achieve"), dict)
                and isinstance(res["Achieve"].get("achieve"), dict)
                else ()
            )
            for a in _ach if isinstance(_ach, (list, tuple)) else ():
                if isinstance(a, dict):
                    need[a.get("i_d")] = a.get("count_param", 1)
            for info in target_cfg.get("world_level_info", ()):
                a_id = info.get("achieve_i_d")
                if not a_id:
                    continue
                achieve_b = db.get_achieve(session.player_id, a_id)
                if not achieve_b:
                    rsp.status = StatusCode.StatusCode_WORLD_LEVEL_ACHIEVE_NOT_FINISH
                    rsp.world_level = current
                    session.send(MsgId.UnlockWorldLevelRsp, rsp, packet_id)
                    return
                achieve = Achieve()
                achieve.ParseFromString(achieve_b)
                if achieve.count < need.get(a_id, 1):
                    rsp.status = StatusCode.StatusCode_WORLD_LEVEL_ACHIEVE_NOT_FINISH
                    rsp.world_level = current
                    session.send(MsgId.UnlockWorldLevelRsp, rsp, packet_id)
                    return

        # 只升不降, 解锁到请求的世界等级
        new_level = max(current, req.world_level)
        if new_level != current:
            db.set_players_info(session.player_id, "world_level", new_level)
        rsp.world_level = new_level

        session.send(
            MsgId.UnlockWorldLevelRsp, rsp, packet_id
        )  # 解锁世界等级 1525 1526
