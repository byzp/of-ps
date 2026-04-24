from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

from proto.net_pb2 import (
    ShopBuyReq,
    ShopBuyRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
    EBagItemTag,
)

import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ShopBuyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ShopBuyReq()
        req.ParseFromString(data)

        rsp = ShopBuyRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.shop_id = req.shop_id
        rsp.grids.id = req.shop_id
        rsp.grids.grid_id = req.grid_id
        rsp.grids.pool_index = 1
        rsp.grids.buy_times = req.buy_times

        for data in res["Shop"]["grid"]["datas"]:
            if data["i_d"] == req.shop_id:  # TODO 如果含有武器, 可能引起严重错误
                rsp1 = PackNotice()
                rsp1.status = StatusCode.StatusCode_OK
                for items in data["items"]:
                    if items["grid_i_d"] == req.grid_id:
                        for pool in res["Shop"]["pool"]["datas"]:
                            if pool["i_d"] == items["shop_pool_i_d"]:
                                rsp.grids.pool_id = pool["i_d"]
                                for item_pool in pool["items"]:
                                    cur_use = {}
                                    for currency in item_pool.get(
                                        "shop_currency_item", []
                                    ):
                                        cur_t = db.get_item_detail(
                                            session.player_id, currency["currency_i_d"]
                                        )
                                        cur_item = ItemDetail()
                                        if not cur_t:
                                            make_item(
                                                currency["currency_i_d"],
                                                0,
                                                session.player_id,
                                                cur_item,
                                            )
                                        else:
                                            cur_item.ParseFromString(cur_t)
                                        num = cur_item.main_item.base_item.num
                                        cur = currency["price"] * req.buy_times
                                        if (
                                            num < cur
                                            and currency["currency_i_d"] == 102
                                        ):  # 使用菱石补齐星石
                                            cur_t = db.get_item_detail(
                                                session.player_id, 108
                                            )
                                            if not cur_t:
                                                rsp.status = (
                                                    StatusCode.StatusCode_ITEM_NOT_ENOUGH
                                                )
                                                session.send(
                                                    MsgId.ShopBuyRsp, rsp, packet_id
                                                )
                                                return
                                            else:
                                                item_t = ItemDetail()
                                                item_t.ParseFromString(cur_t)
                                                if (
                                                    item_t.main_item.base_item.num + num
                                                    < cur
                                                ):
                                                    rsp.status = (
                                                        StatusCode.StatusCode_ITEM_NOT_ENOUGH
                                                    )
                                                    session.send(
                                                        MsgId.ShopBuyRsp, rsp, packet_id
                                                    )
                                                    return
                                                else:
                                                    item_t.main_item.base_item.num -= (
                                                        cur - num
                                                    )
                                                    db.set_item_detail(
                                                        session.player_id,
                                                        item_t.SerializeToString(),
                                                        108,
                                                    )
                                                    cur_item.main_item.base_item.num = (
                                                        cur
                                                    )
                                                    rsp1.items.add().CopyFrom(item_t)
                                        if cur_item.main_item.base_item.num < cur:
                                            rsp.status = (
                                                StatusCode.StatusCode_ITEM_NOT_ENOUGH
                                            )
                                            session.send(
                                                MsgId.ShopBuyRsp, rsp, packet_id
                                            )
                                            return
                                        cur_item.main_item.base_item.num -= cur
                                        cur_use[currency["currency_i_d"]] = cur_item
                                    for k, v in cur_use.items():
                                        db.set_item_detail(
                                            session.player_id,
                                            v.SerializeToString(),
                                            k,
                                            None,
                                        )
                                        rsp1.items.add().CopyFrom(v)
                                    item = db.get_item_detail(
                                        session.player_id, item_pool["item_i_d"]
                                    )
                                    tmp1 = ItemDetail()
                                    if not item:
                                        make_item(
                                            item_pool["item_i_d"],
                                            0,
                                            session.player_id,
                                            tmp1,
                                        )
                                    else:
                                        tmp1.ParseFromString(item)
                                    is_base_item = (
                                        tmp1.main_item.item_tag
                                        != EBagItemTag.EBagItemTag_Weapon
                                    )
                                    if is_base_item:
                                        num_t = tmp1.main_item.base_item.num
                                        tmp1.main_item.base_item.num = item_pool[
                                            "item_num"
                                        ]
                                        rsp.items.add().CopyFrom(tmp1)
                                        tmp1.main_item.base_item.num = (
                                            num_t
                                            + item_pool["item_num"] * req.buy_times
                                        )
                                    else:
                                        # TODO 一次购买多份武器或映像
                                        rsp.items.add().CopyFrom(tmp1)
                                    rsp1.items.add().CopyFrom(
                                        tmp1
                                    )  # TODO 目前是直接给礼包，不会自动开启
                                    if is_base_item:
                                        db.set_item_detail(
                                            session.player_id,
                                            tmp1.SerializeToString(),
                                            item_pool["item_i_d"],
                                            None,
                                        )
                                    else:
                                        db.set_item_detail(
                                            session.player_id,
                                            tmp1.SerializeToString(),
                                            None,
                                            tmp1.main_item.weapon.instance_id,  # TODO 尚未考虑映像
                                        )
        session.send(MsgId.ShopBuyRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
