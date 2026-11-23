from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import random

from proto.net_pb2 import (
    TreasureDigReq,
    TreasureDigRsp,
    StatusCode,
    PackNotice,
)

from utils.res_loader import res
import utils.db as db
from utils.reward_resolver import resolve_reward
from utils import item_mgr

"""
# 考古挖宝 4521 4522
# treasure_id = 藏宝图物品 id(Treasure.json treasure: 5070001 普通/5070002 高级)
"""


def _shovel_cfgs():
    """Shovel.json shovel: (item_i_d, success_rate 千分比, excavate_time)"""
    return res.get("Shovel", {}).get("shovel", {}).get("datas", ())


@packet_handler(MsgId.TreasureDigReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureDigReq()
        req.ParseFromString(data)

        rsp = TreasureDigRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.treasure_id = req.treasure_id

        # 校验藏宝图配置(Treasure.json treasure)
        if not any(
            e.get("i_d") == req.treasure_id
            for e in res.get("Treasure", {}).get("treasure", {}).get("datas", ())
        ):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.TreasureDigRsp, rsp, packet_id)  # 4521,4522
            return

        # 需要持有宝具铲(Shovel.json, 工具不消耗), 取已持有中成功率最高的一把
        best_rate = -1
        for cfg in _shovel_cfgs():
            item_id = cfg.get("item_i_d", 0)
            if item_id and item_mgr.get_num(session.player_id, item_id) > 0:
                best_rate = max(best_rate, cfg.get("success_rate", 0))
        if best_rate < 0:
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.TreasureDigRsp, rsp, packet_id)  # 4521,4522
            return

        pack = PackNotice()
        pack.status = StatusCode.StatusCode_OK

        # 消耗 1 张藏宝图(treasure_id 即背包物品 id)
        if not item_mgr.consume_items(
            session.player_id,
            [(req.treasure_id, 1)],
            pack_notice=pack,
            session=session,
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            session.send(MsgId.TreasureDigRsp, rsp, packet_id)  # 4521,4522
            return

        # 按铲子成功率(千分比: 500/800/1000)判定成败
        rsp.success = random.randint(1, 1000) <= best_rate
        player_level = db.get_players_info(session.player_id, "level")[0]
        if rsp.success:
            pool_id = random.choice(
                Config.DIG_POOLS.get(req.treasure_id, Config.DIG_POOLS[5070001])
            )
        else:
            pool_id = Config.FAIL_POOL  # 失败也给一份"土渣"
        # 池内为同类物品的随机抽取池(单池含 10/500 个碎片/章节条目),
        # resolve_reward 返回全部条目, 这里随机取一条作为本次挖掘产出
        items = resolve_reward(pool_id, player_level)
        if items:
            chosen = random.choice(items)
            item_mgr.grant_items(
                session.player_id,
                [chosen],
                rsp_items=rsp.rewards,
                pack_notice=pack,
                session=session,
            )
            # 考古进度: 按奖池累计挖掘次数(kv ns=archaeology)
            db.incr_kv(session.player_id, "archaeology", str(chosen[0]), 1)

        session.send(MsgId.TreasureDigRsp, rsp, packet_id)  # 4521,4522
        session.send(MsgId.PackNotice, pack, 0)
