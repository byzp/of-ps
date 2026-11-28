from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

import random

from proto.net_pb2 import (
    TreasureDigReq,
    TreasureDigRsp,
    StatusCode,
    PackNotice,
    ItemDetail,
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


def _consume_treasure(player_id, item_id, pack):
    """藏宝图可能按唯一物品存储; 在调用方玩家锁和事务内消费一张。"""
    row = item_mgr.item_config(item_id)
    if row.get("new_bag_item_tag") not in Config.ITEM_MGR_UNIQUE_TAGS:
        return item_mgr.consume_items(player_id, [(item_id, 1)], pack_notice=pack)
    raw_items = [
        blob for blob in db.get_item_detail(player_id)
        if ItemDetail.FromString(blob).main_item.item_id == item_id
    ]
    if not raw_items:
        return False
    if len(raw_items) != 1:
        raise item_mgr.EconomyConfigError("duplicate unique treasure map state")
    detail = ItemDetail.FromString(raw_items[0])
    item_mgr.validate_pickup_item(detail)
    if detail.main_item.item_tag != row.get("new_bag_item_tag"):
        raise item_mgr.EconomyConfigError("treasure map tag mismatch")
    which = detail.main_item.WhichOneof("item")
    if which == "base_item":
        if detail.main_item.base_item.item_id != item_id or detail.main_item.base_item.num != 1:
            raise item_mgr.EconomyConfigError("invalid unique treasure map state")
        db.db.execute(
            "DELETE FROM items WHERE player_id=? AND item_id=?", (player_id, item_id)
        )
        detail.main_item.base_item.num = 0
    else:
        instance_id = getattr(detail.main_item, which).instance_id
        db.del_item_detail(player_id, instance_id)
    pack.items.add().CopyFrom(detail)
    return True


@packet_handler(MsgId.TreasureDigReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = TreasureDigReq()
        req.ParseFromString(data)

        rsp = TreasureDigRsp()
        rsp.treasure_id = req.treasure_id
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            # 校验藏宝图配置(Treasure.json treasure)
            if not any(
                e.get("i_d") == req.treasure_id
                for e in res.get("Treasure", {}).get("treasure", {}).get("datas", ())
            ):
                raise item_mgr.EconomyConfigError("missing treasure config")
            if req.treasure_id not in Config.DIG_POOLS:
                raise item_mgr.EconomyConfigError("missing treasure dig pool")

            # 需要持有宝具铲(Shovel.json, 工具不消耗), 取已持有中成功率最高的一把。
            best_rate = -1
            for cfg in _shovel_cfgs():
                item_id = cfg.get("item_i_d", 0)
                rate = item_mgr.validate_counter(
                    cfg.get("success_rate", 0), label="shovel success rate"
                )
                if rate > 1000:
                    raise item_mgr.EconomyConfigError("invalid shovel success rate")
                if item_id and item_mgr.get_num(session.player_id, item_id) > 0:
                    best_rate = max(best_rate, rate)
            if best_rate < 0:
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            else:
                rsp.success = random.randint(1, 1000) <= best_rate
                player_level = db.get_players_info(session.player_id, "level")[0]
                pool_id = random.choice(Config.DIG_POOLS[req.treasure_id]) if rsp.success else Config.FAIL_POOL
                items = resolve_reward(pool_id, player_level)
                if not items:
                    raise item_mgr.EconomyConfigError("missing treasure dig reward")
                chosen = random.choice(items)
                item_mgr.validate_rewards([chosen])
                with item_mgr.player_lock(session.player_id), item_mgr.deferred_notifications(), db.transaction():
                    if not _consume_treasure(
                        session.player_id, req.treasure_id, pack
                    ):
                        rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                    else:
                        item_mgr.grant_items(
                            session.player_id,
                            [chosen],
                            rsp_items=rsp.rewards,
                            pack_notice=pack,
                            session=session,
                        )
                        db.incr_kv(session.player_id, "archaeology", str(chosen[0]), 1)
                        rsp.status = StatusCode.StatusCode_OK
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.rewards[:]
            del pack.items[:]

        session.send(MsgId.TreasureDigRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK and pack.items:
            session.send(MsgId.PackNotice, pack, 0)
