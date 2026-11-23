from config import Config
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BuyGameCoinReq,
    BuyGameCoinRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.pb_create import make_item


@packet_handler(MsgId.BuyGameCoinReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BuyGameCoinReq()
        req.ParseFromString(data)

        rsp = BuyGameCoinRsp()
        rsp.status = StatusCode.StatusCode_OK

        cfg = {}
        if (
            "GlobalConfig" in res
            and "config" in res["GlobalConfig"]
            and "datas" in res["GlobalConfig"]["config"]
        ):
            for e in res["GlobalConfig"]["config"]["datas"]:
                if e.get("key") in (
                    "GameCoinBuy",
                    "GameCoinMax",
                    "GameCoinIni",
                    "GameCoinTimeRecover",
                ):
                    cfg[e["key"]] = e.get("values") or ()
        buy = cfg.get("GameCoinBuy", ())
        if len(buy) >= 3:
            currency_id, cost_per, coin_per = int(buy[0]), int(buy[1]), int(buy[2])
        else:
            currency_id, cost_per, coin_per = Config.BUY_GAME_COIN_FALLBACK_BUY
        coin_max = (
            int(cfg["GameCoinMax"][0])
            if cfg.get("GameCoinMax")
            else Config.GAME_COIN_MAX_FALLBACK
        )
        coin_ini = (
            int(cfg["GameCoinIni"][0])
            if cfg.get("GameCoinIni")
            else Config.GAME_COIN_INITIAL_FALLBACK
        )
        recover_sec = (
            int(cfg["GameCoinTimeRecover"][0])
            if cfg.get("GameCoinTimeRecover")
            else Config.GAME_COIN_RECOVER_SECONDS_FALLBACK
        )
        if recover_sec <= 0:
            recover_sec = Config.GAME_COIN_RECOVER_SECONDS_FALLBACK

        buy_count = req.buy_count if req.buy_count > 0 else 1
        now = int(time.time())
        player_id = session.player_id

        # 惰性恢复结算: kv ns=game_coin 存 last_recover_ts;
        with item_mgr.player_lock(player_id):
            coin_item = ItemDetail()
            coin_b = db.get_item_detail(player_id, Config.GAME_COIN_ITEM_ID)
            if coin_b:
                coin_item.ParseFromString(coin_b)
            else:
                make_item(Config.GAME_COIN_ITEM_ID, 0, player_id, coin_item)
            held = coin_item.main_item.base_item.num

            last_ts = db.get_kv(player_id, "game_coin", "last_recover_ts")
            recovered = held
            if last_ts is None:
                # 首次结算: 发放初始游戏币
                recovered = max(held, coin_ini)
                db.set_kv(player_id, "game_coin", "last_recover_ts", now)
            elif held >= coin_max:
                # 已满时不累计恢复进度
                db.set_kv(player_id, "game_coin", "last_recover_ts", now)
            else:
                gain = (now - int(last_ts)) // recover_sec
                if gain > 0:
                    recovered = min(held + gain, coin_max)
                    # 满了归零计时, 未满保留余数继续计时
                    if recovered >= coin_max:
                        db.set_kv(player_id, "game_coin", "last_recover_ts", now)
                    else:
                        db.set_kv(
                            player_id,
                            "game_coin",
                            "last_recover_ts",
                            int(last_ts) + gain * recover_sec,
                        )
            if recovered != held:
                held = recovered
                coin_item.main_item.base_item.num = held
                db.set_item_detail(
                    player_id,
                    coin_item.SerializeToString(),
                    Config.GAME_COIN_ITEM_ID,
                    None,
                )

        # 超过 GameCoinMax 的部分不允许购买(恢复与购买都以持有上限为界)
        if held >= coin_max:
            rsp.status = StatusCode.StatusCode_FAIL  # 已达 GameCoinMax 持有上限
            rsp.item_details.add().CopyFrom(coin_item)
            session.send(MsgId.BuyGameCoinRsp, rsp, packet_id)  # 2531,2532
            return
        # 购买份数按剩余空间截断
        buy_count = min(buy_count, (coin_max - held + coin_per - 1) // coin_per)

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK

        # 扣星石(GameCoinBuy 档位, 不足回 ITEM_NOT_ENOUGH)
        cost = cost_per * buy_count
        if not item_mgr.consume_items(
            player_id, [(currency_id, cost)], pack_notice=rsp1, session=session
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.BuyGameCoinRsp, rsp, packet_id)  # 2531,2532
            return
        for detail in rsp1.items:
            rsp.item_details.add().CopyFrom(detail)

        # 发放游戏币(封顶 GameCoinMax; 买满后计时归零)
        with item_mgr.player_lock(player_id):
            coin_item = ItemDetail()
            coin_b = db.get_item_detail(player_id, Config.GAME_COIN_ITEM_ID)
            if coin_b:
                coin_item.ParseFromString(coin_b)
            else:
                make_item(Config.GAME_COIN_ITEM_ID, 0, player_id, coin_item)
            new_num = min(
                coin_item.main_item.base_item.num + coin_per * buy_count, coin_max
            )
            coin_item.main_item.base_item.num = new_num
            item_mgr.mark_new_item(player_id, coin_item)
            db.set_item_detail(
                player_id, coin_item.SerializeToString(), Config.GAME_COIN_ITEM_ID, None
            )
            if new_num >= coin_max:
                db.set_kv(player_id, "game_coin", "last_recover_ts", now)
        rsp.item_details.add().CopyFrom(coin_item)
        rsp1.items.add().CopyFrom(coin_item)

        session.send(MsgId.BuyGameCoinRsp, rsp, packet_id)  # 购买游戏币 2531 2532
        session.send(MsgId.PackNotice, rsp1, 0)
