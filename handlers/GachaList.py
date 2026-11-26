from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import pickle

from proto.net_pb2 import GachaListReq, GachaListRsp, StatusCode
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
            # 保底剩余：默认所有卡池共享同一个计数（Config.GACHA_PITY_SHARED）
            type_id = int(data.get("new_u_i_gacha_type") or 2)
            tmp.guarantee = gacha_prob.remaining(
                session.player_id, data["i_d"], type_id, data
            )
            # 自选UP物品(OptionalUpPoolItem 持久化)
            raw = db.get_kv(session.player_id, "gacha_optional_up", str(data["i_d"]))
            if raw:
                up = pickle.loads(raw)
                tmp.optional_up_item = up.get("item_id", 0)
                tmp.choose_pool_id = up.get("pool_id", 0)
        session.send(MsgId.GachaListRsp, rsp, packet_id)  # 1443,1444
