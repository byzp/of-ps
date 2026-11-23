from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    WishListBuyReq,
    WishListBuyRsp,
    WishListBuyNotice,
    ItemDetail,
    PackNotice,
    EBagItemTag,
    StatusCode,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.pb_create import make_item
from server.scene_data import get_session
import server.photo_share as ps


@packet_handler(MsgId.WishListBuyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = WishListBuyReq()
        req.ParseFromString(data)

        rsp = WishListBuyRsp()
        rsp.player_id = req.player_id
        rsp.info.CopyFrom(req.info)

        target_player_id = req.player_id
        shop_id = req.info.shop_id
        grid_id = req.info.grid_id

        # ShopBuy 的简化版: 扣自己的货币, 把商品发给心愿单好友
        buyer_notice = PackNotice()  # 通知买家货币变化
        buyer_notice.status = StatusCode.StatusCode_OK
        target_notice = PackNotice()  # 通知受赠好友背包变化
        target_notice.status = StatusCode.StatusCode_OK

        found = False
        pool_id = 0
        # 仿 ShopBuy: 先全量校验并把扣减/发放暂存内存, 全部通过后再统一落库,
        # 任何失败 return 都发生在第一笔写库之前, 避免多货币时白扣钱无法回滚
        cur_use = {}  # currency_i_d -> 扣减后的买家货币 ItemDetail
        gift_items = {}  # item_i_d -> 累加后的受赠好友普通物品 ItemDetail
        gift_weapons = []  # (instance_id, ItemDetail) 武器/映像类
        for grid in res["Shop"]["grid"]["datas"]:
            if grid.get("i_d") != shop_id:
                continue
            for grid_item in grid.get("items", []):
                if grid_item.get("grid_i_d") != grid_id:
                    continue
                for pool in res["Shop"]["pool"]["datas"]:
                    if pool.get("i_d") != grid_item.get("shop_pool_i_d"):
                        continue
                    found = True
                    pool_id = pool["i_d"]
                    for item_pool in pool.get("items", []):
                        # 1. 校验买家货币, 扣减暂存(同种货币跨条目累计)
                        for currency in item_pool.get("shop_currency_item", []):
                            # 缺省货币为金币(部分 Shop 条目无 currency_i_d)
                            cur_id = currency.get("currency_i_d", 101)
                            cur_item = cur_use.get(cur_id)
                            if cur_item is None:
                                cur_b = db.get_item_detail(session.player_id, cur_id)
                                cur_item = ItemDetail()
                                if not cur_b:
                                    make_item(cur_id, 0, session.player_id, cur_item)
                                else:
                                    cur_item.ParseFromString(cur_b)
                            price = currency["price"]
                            have = cur_item.main_item.base_item.num
                            if have < price:
                                # 菱石补齐: 每 1 点缺口需 5 菱石(GameCoinBuy '102','5','1')
                                shortfall = price - have
                                diamonds = shortfall * 5
                                if not item_mgr.consume_items(
                                    session.player_id,
                                    [(102, diamonds)],
                                    pack_notice=buyer_notice,
                                    session=session,
                                ):
                                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                                    session.send(MsgId.WishListBuyRsp, rsp, packet_id)
                                    return
                            else:
                                cur_item.main_item.base_item.num -= price
                                cur_use[cur_id] = cur_item
                        # 2. 受赠好友的商品暂存(同种物品跨条目累计)
                        item_id = item_pool["item_i_d"]
                        gift = gift_items.get(item_id)
                        if gift is None:
                            item_b = db.get_item_detail(target_player_id, item_id)
                            gift = ItemDetail()
                            if not item_b:
                                make_item(item_id, 0, target_player_id, gift)
                            else:
                                gift.ParseFromString(item_b)
                        if gift.main_item.item_tag != EBagItemTag.EBagItemTag_Weapon:
                            gift.main_item.base_item.num += item_pool["item_num"]
                            gift_items[item_id] = gift
                        else:
                            # 武器/映像等实例类商品: 单独分配 instance_id 落库
                            granted = item_mgr.grant_single_item(
                                target_player_id,
                                item_id,
                                num=item_pool.get("item_num", 1),
                                pack_notice=target_notice,
                            )
                            which = granted.main_item.WhichOneof("item")
                            if which:
                                inst = getattr(granted.main_item, which)
                                if hasattr(inst, "instance_id") and inst.instance_id:
                                    gift_weapons.append((inst.instance_id, granted))

        if not found:
            rsp.status = StatusCode.StatusCode_WISH_LIST_SHOP_ERR
            session.send(MsgId.WishListBuyRsp, rsp, packet_id)
            return

        # 全部校验通过, 统一落库
        for cur_id, cur_item in cur_use.items():
            db.set_item_detail(session.player_id, cur_item.SerializeToString(), cur_id)
            buyer_notice.items.add().CopyFrom(cur_item)
        for item_id, gift in gift_items.items():
            item_mgr.mark_new_item(target_player_id, gift)
            db.set_item_detail(target_player_id, gift.SerializeToString(), item_id)
            target_notice.items.add().CopyFrom(gift)
        for instance_id, gift in gift_weapons:
            db.set_item_detail(
                target_player_id, gift.SerializeToString(), None, instance_id
            )
            target_notice.items.add().CopyFrom(gift)

        # 从好友心愿单移除该项, 并累计本周赠送次数
        with ps.lock_wish:
            ps.wish_lists.get(target_player_id, {}).pop((shop_id, grid_id), None)
            ps.week_send_count[session.player_id] = (
                ps.week_send_count.get(session.player_id, 0) + 1
            )
            rsp.week_send_count = ps.week_send_count[session.player_id]

        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.WishListBuyRsp, rsp, packet_id)  # 2689,2690
        session.send(MsgId.PackNotice, buyer_notice, 0)

        # 受赠好友在线则推送通知
        for s in get_session():
            if s.player_id == target_player_id:
                notice = WishListBuyNotice()
                notice.status = StatusCode.StatusCode_OK
                notice.shop_id = shop_id
                notice.grids.id = shop_id
                notice.grids.grid_id = grid_id
                notice.grids.pool_id = pool_id
                s.send(MsgId.WishListBuyNotice, notice, 0)  # 2688
                s.send(MsgId.PackNotice, target_notice, 0)
                break
