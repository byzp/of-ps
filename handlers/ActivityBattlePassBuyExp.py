from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    ActivityBattlePassBuyExpReq,
    ActivityBattlePassBuyExpRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils.res_loader import res


def _buy_exp_cfg():
    for e in res.get("GlobalConfig", {}).get("config", {}).get("datas", ()) or ():
        if e.get("key") == "BattlePass_BuyExp_Currency":
            values = e.get("values") or ()
            if values:
                parts = values[0].split(":")
                if len(parts) == 3 and all(p.strip().isdigit() for p in parts):
                    cur, cost, exp = parts
                    return int(cur), int(cost), int(exp)
                return Config.ACTIVITY_BATTLE_PASS_BUY_EXP_FALLBACK_BUY
    return Config.ACTIVITY_BATTLE_PASS_BUY_EXP_FALLBACK_BUY


@packet_handler(MsgId.ActivityBattlePassBuyExpReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ActivityBattlePassBuyExpReq()
        req.ParseFromString(data)

        rsp = ActivityBattlePassBuyExpRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.activity_battle_pass_id = req.activity_battle_pass_id

        currency_id, cost, add_exp = _buy_exp_cfg()

        # 扣购买货币(不足回 ITEM_NOT_ENOUGH)
        cur_item = ItemDetail()
        cur_b = db.get_item_detail(session.player_id, currency_id)
        if cur_b:
            cur_item.ParseFromString(cur_b)
        if cur_item.main_item.base_item.num < cost:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.ActivityBattlePassBuyExpRsp, rsp, packet_id)  # 2131,2132
            return
        cur_item.main_item.base_item.num -= cost
        db.set_item_detail(
            session.player_id, cur_item.SerializeToString(), currency_id, None
        )
        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK
        pack.items.add().CopyFrom(cur_item)

        # BattlePass.battle_pass.battle_pass_level_ups 各级 exp 均为 1000,
        # 与 Config.BP_EXP_PER_LEVEL 一致; 战令经验持久化到 player_kv
        lv, total, cur = db.bp_add_exp(
            session.player_id, req.activity_battle_pass_id, add_exp
        )
        rsp.battle_pass_lv = lv
        rsp.total_exp = total
        rsp.current_exp = cur

        session.send(MsgId.ActivityBattlePassBuyExpRsp, rsp, packet_id)  # 2131,2132
        session.send(MsgId.PackNotice, pack, 0)
