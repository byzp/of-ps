from config import Config
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    PlayerVitalityBuyReq,
    PlayerVitalityBuyRsp,
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


@packet_handler(MsgId.PlayerVitalityBuyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = PlayerVitalityBuyReq()
        req.ParseFromString(data)

        rsp = PlayerVitalityBuyRsp()
        rsp.status = StatusCode.StatusCode_OK

        # 当日购买次数持久化(kv ns=buy, 按天 key 自然过期)
        day = str(refresh.day_index())
        buy_key = f"vitality:{day}"
        times = int(db.get_kv(session.player_id, "buy", buy_key, 0) or 0)

        # 体力上限按玩家等级查 Level.player_level.player_vitality(50级=150)
        vitality_max = Config.VITALITY_MAX_FALLBACK
        _infos = db.get_players_info(session.player_id, "level") or []
        if _infos and (
            "Level" in res
            and "player_level" in res["Level"]
            and "datas" in res["Level"]["player_level"]
        ):
            level = _infos[0]
            for e in res["Level"]["player_level"]["datas"]:
                if e.get("i_d") == level:
                    vitality_max = e.get(
                        "player_vitality", Config.VITALITY_MAX_FALLBACK
                    )
                    break

        # 先读体力, 已满时不扣星石直接失败
        if item_mgr.get_num(session.player_id, Config.VITALITY_ITEM_ID) >= vitality_max:
            rsp.status = StatusCode.StatusCode_VITALITY_FULL
            rsp.vitality_buy_num = times
            session.send(MsgId.PlayerVitalityBuyRsp, rsp, packet_id)  # 1623,1624
            return

        currency_id, cost, add = Config.PLAYER_VITALITY_BUY_FALLBACK_TIER
        if (
            "GlobalConfig" in res
            and "config" in res["GlobalConfig"]
            and "datas" in res["GlobalConfig"]["config"]
        ):
            for e in res["GlobalConfig"]["config"]["datas"]:
                if e.get("key") == "Player_Vitality_Buy_Times":
                    values = e.get("values") or ()
                    if values:
                        v = values[min(times, len(values) - 1)]
                        parts = v.split(":")
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
            rsp.vitality_buy_num = times
            session.send(MsgId.PlayerVitalityBuyRsp, rsp, packet_id)  # 1623,1624
            return

        # 增加体力(按等级上限封顶, 封顶发放走 player_lock 后直读 db)
        with item_mgr.player_lock(session.player_id):
            item = ItemDetail()
            item_b = db.get_item_detail(session.player_id, Config.VITALITY_ITEM_ID)
            if item_b:
                item.ParseFromString(item_b)
            else:
                make_item(Config.VITALITY_ITEM_ID, 0, session.player_id, item)
            item.main_item.base_item.num = min(
                item.main_item.base_item.num + add, vitality_max
            )
            db.set_item_detail(
                session.player_id,
                item.SerializeToString(),
                Config.VITALITY_ITEM_ID,
                None,
            )
        rsp.items.add().CopyFrom(item)
        rsp1.items.add().CopyFrom(item)

        rsp.vitality_buy_num = db.incr_kv(session.player_id, "buy", buy_key, 1)

        achieve_track.report(session, "vitality_restore")

        session.send(MsgId.PlayerVitalityBuyRsp, rsp, packet_id)  # 购买体力 1623 1624
        session.send(MsgId.PackNotice, rsp1, 0)
