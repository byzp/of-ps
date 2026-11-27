import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import BossRushTerminateChallengeReq, BossRushTerminateChallengeRsp, StatusCode
from server import boss_rush
import utils.db as db


@packet_handler(MsgId.BossRushTerminateChallengeReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushTerminateChallengeReq()
        req.ParseFromString(data)
        rsp = BossRushTerminateChallengeRsp(season_id=req.season_id)
        season_data = boss_rush.season(req.season_id)
        if season_data is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.BossRushTerminateChallengeRsp, rsp, packet_id)
            return
        with boss_rush.lock, db.transaction():
            info, run, dirty = boss_rush.load_state(session.player_id, season_data)
            if dirty:
                boss_rush.save_state(session.player_id, req.season_id, info, run)
            if not boss_rush.run_active(run) or run.get("season_id") != req.season_id:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushTerminateChallengeRsp, rsp, packet_id)
                return
            boss_rush.settle(info)
            run["status"] = "settled"
            run["settled_at_ms"] = int(time.time() * 1000)
            run["team"] = []
            boss_rush.save_state(session.player_id, req.season_id, info, run)
            db.del_kv(session.player_id, "boss_rush", f"{req.season_id}:battle_start")
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.BossRushTerminateChallengeRsp, rsp, packet_id)
