from config import Config
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PlayerEnergyBuyReq,
    PlayerEnergyBuyRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.pb_create import make_item
from utils import refresh
from utils import achieve_track


@packet_handler(MsgId.PlayerEnergyBuyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerEnergyBuyReq()
        req.ParseFromString(data)

        rsp = PlayerEnergyBuyRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 当日购买次数持久化(kv ns=buy, 按天 key 自然过期)
        day = str(refresh.day_index())
        buy_key = f"energy:{day}"
        times = int(db.get_kv(session.player_id, "buy", buy_key, 0) or 0)

        # 精力上限按玩家等级查 Level.player_level.player_energy(50级=800)
        energy_max = Config.ENERGY_MAX_FALLBACK
        row = db.get_players_info(session.player_id, "level")
        if row:
            level = row[0]
            for e in res.get("Level", {}).get("player_level", {}).get("datas") or ():
                if e.get("i_d") == level:
                    energy_max = e.get("player_energy", Config.ENERGY_MAX_FALLBACK)
                    break

        # 先读精力, 已满时不扣星石直接失败(无精力已满专用错误码, 用 FAIL)
        if item_mgr.get_num(session.player_id, Config.ENERGY_ITEM_ID) >= energy_max:
            rsp.status = StatusCode.StatusCode_FAIL
            rsp.energy_buy_num = times
            session.send(MsgId.PlayerEnergyBuyRsp, rsp, packet_id)  # 1053,1054
            return

        currency_id, cost, add = Config.PLAYER_ENERGY_BUY_FALLBACK_TIER
        for e in res.get("GlobalConfig", {}).get("config", {}).get("datas") or ():
            if e.get("key") == "Player_Energy_Buy_Times":
                values = e.get("values") or ()
                if values:
                    parts = values[min(times, len(values) - 1)].split(":")
                    if len(parts) == 3:
                        currency_id, cost, add = (
                            int(parts[0]),
                            int(parts[1]),
                            int(parts[2]),
                        )
                break

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        if not item_mgr.consume_items(
            session.player_id,
            [(currency_id, cost)],
            pack_notice=rsp1,
            session=session,
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            rsp.energy_buy_num = times
            session.send(MsgId.PlayerEnergyBuyRsp, rsp, packet_id)  # 1053,1054
            return

        # 增加精力(按等级上限封顶, 封顶发放走 player_lock 后直读 db)
        with item_mgr.player_lock(session.player_id):
            item = ItemDetail()
            item_b = db.get_item_detail(session.player_id, Config.ENERGY_ITEM_ID)
            if item_b:
                item.ParseFromString(item_b)
            else:
                make_item(Config.ENERGY_ITEM_ID, 0, session.player_id, item)
            item.main_item.base_item.num = min(
                item.main_item.base_item.num + add, energy_max
            )
            db.set_item_detail(
                session.player_id, item.SerializeToString(), Config.ENERGY_ITEM_ID, None
            )
        rsp.items.add().CopyFrom(item)
        rsp1.items.add().CopyFrom(item)

        rsp.energy_buy_num = db.incr_kv(session.player_id, "buy", buy_key, 1)

        achieve_track.report(session, "energy_restore")

        session.send(MsgId.PlayerEnergyBuyRsp, rsp, packet_id)  # 购买精力 1053 1054
        session.send(MsgId.PackNotice, rsp1, 0)
