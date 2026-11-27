from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import pickle

from proto.net_pb2 import GachaListReq, GachaListRsp, StatusCode
from handlers.Gacha import _configuration
from utils.res_loader import res
from config import Config
import utils.db as db
from utils import gacha_prob


@packet_handler(MsgId.GachaListReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        rsp = GachaListRsp()
        rsp.status = StatusCode.StatusCode_OK
        rows = {row["i_d"]: row for row in res["Gacha"]["info"]["datas"]}
        for gacha_id in Config.GACHA_VISIBLE_IDS:
            data = rows.get(gacha_id)
            if not data:
                continue
            tmp = rsp.gachas.add()
            tmp.gacha_id = data["i_d"]
            tmp.gacha_times = db.get_total_gacha_num(session.player_id, data["i_d"])
            configuration = _configuration(data["i_d"])
            if configuration:
                _, normal, guarantee = configuration
                claimed = set(db.get_claimed(session.player_id, "gacha_full_pick"))
                eligible = {str(item_id) for item_id in normal + guarantee}
                tmp.has_full_pick = tmp.gacha_times >= Config.FULL_PICK_MIN_DRAWS and bool(eligible - claimed)
            if data.get("big_guarantee_pool_i_d"):
                cap = int(data.get("max_times", 0) or 70)
                tmp.guarantee = max(
                    0, cap - db.get_gacha_guarantee(session.player_id, data["i_d"])
                )
            # 自选UP物品(OptionalUpPoolItem 持久化)
            raw = db.get_kv(session.player_id, "gacha_optional_up", str(data["i_d"]))
            if raw:
                up = pickle.loads(raw)
                tmp.optional_up_item = up.get("item_id", 0)
                tmp.choose_pool_id = up.get("pool_id", 0)
        session.send(MsgId.GachaListRsp, rsp, packet_id)  # 1443,1444
