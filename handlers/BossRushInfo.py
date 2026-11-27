import time

from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import BossRushInfoReq, BossRushInfoRsp, StatusCode
from server import boss_rush
import utils.db as db


@packet_handler(MsgId.BossRushInfoReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushInfoReq()
        req.ParseFromString(data)
        rsp = BossRushInfoRsp()
        now = int(time.time())
        season_data = boss_rush.current_season(now) if req.season_id == 0 else boss_rush.season(req.season_id)
        if season_data is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.BossRushInfoRsp, rsp, packet_id)
            return
        with boss_rush.lock, db.transaction():
            info, run, dirty = boss_rush.load_state(session.player_id, season_data, now)
            if dirty:
                boss_rush.save_state(session.player_id, season_data["i_d"], info, run)
            # 同时保存结构升级后的信息（例如新增配置阶段）。
            elif not db.get_boss_rush_info(session.player_id, season_data["i_d"]):
                db.set_boss_rush_info(session.player_id, season_data["i_d"], info.SerializeToString())
        rsp.status = StatusCode.StatusCode_OK
        rsp.info.CopyFrom(info)
        session.send(MsgId.BossRushInfoRsp, rsp, packet_id)
