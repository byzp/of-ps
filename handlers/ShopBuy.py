from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
import logging

import proto.OverField_pb2 as ShopBuyReq_pb2
import proto.OverField_pb2 as ShopBuyRsp_pb2
import proto.OverField_pb2 as ItemDetail
import proto.OverField_pb2 as PackNotice_pb2
import proto.OverField_pb2 as StatusCode_pb2
import utils.db as db
from utils.res_loader import res
from utils.pb_create import make_item

logger = logging.getLogger(__name__)


@packet_handler(MsgId.ShopBuyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ShopBuyReq_pb2.ShopBuyReq()
        req.ParseFromString(data)

        rsp = ShopBuyRsp_pb2.ShopBuyRsp()
        rsp.status = StatusCode_pb2.StatusCode_OK
        rsp.shop_id = req.shop_id
        rsp.grids.id = req.shop_id
        rsp.grids.grid_id = req.grid_id
        rsp.grids.pool_index = 1
        rsp.grids.buy_times = 1

        for data in res["Shop"]["grid"]["datas"]:
            if data["i_d"] == req.shop_id:  # TODO 如果含有武器, 可能引起严重错误
                rsp1 = PackNotice_pb2.PackNotice()
                rsp1.status = StatusCode_pb2.StatusCode_OK
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
                                        if not cur_t:
                                            cur_t = make_item(
                                                currency["currency_i_d"],
                                                0,
                                                session.player_id,
                                            )
                                        cur_item = ItemDetail.ItemDetail()
                                        cur_item.ParseFromString(cur_t)
                                        num = cur_item.main_item.base_item.num
                                        if (
                                            num < currency["price"]
                                            and currency["currency_i_d"] == 102
                                        ):  # 使用菱石补齐星石
                                            cur_t = db.get_item_detail(
                                                session.player_id, 108
                                            )
                                            if not cur_t:
                                                rsp.status = (
                                                    StatusCode_pb2.StatusCode_ITEM_NOT_ENOUGH
                                                )
                                                session.send(
                                                    MsgId.ShopBuyRsp, rsp, packet_id
                                                )
                                                return
                                            else:
                                                item_t = ItemDetail.ItemDetail()
                                                item_t.ParseFromString(cur_t)
                                                if (
                                                    item_t.main_item.base_item.num + num
                                                    < currency["price"]
                                                ):
                                                    rsp.status = (
                                                        StatusCode_pb2.StatusCode_ITEM_NOT_ENOUGH
                                                    )
                                                    session.send(
                                                        MsgId.ShopBuyRsp, rsp, packet_id
                                                    )
                                                    return
                                                else:
                                                    item_t.main_item.base_item.num -= (
                                                        currency["price"] - num
                                                    )
                                                    db.set_item_detail(
                                                        session.player_id,
                                                        item_t.SerializeToString(),
                                                        108,
                                                    )
                                                    cur_item.main_item.base_item.num = (
                                                        currency["price"]
                                                    )
                                                    rsp1.items.add().CopyFrom(item_t)

                                        if (
                                            cur_item.main_item.base_item.num
                                            < currency["price"]
                                        ):
                                            rsp.status = (
                                                StatusCode_pb2.StatusCode_ITEM_NOT_ENOUGH
                                            )
                                            session.send(
                                                MsgId.ShopBuyRsp, rsp, packet_id
                                            )
                                            return
                                        cur_item.main_item.base_item.num -= currency[
                                            "price"
                                        ]
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
                                    tmp1 = ItemDetail.ItemDetail()
                                    if not item:
                                        item = make_item(
                                            item_pool["item_i_d"], 0, session.player_id
                                        )
                                    tmp1.ParseFromString(item)
                                    num_t = tmp1.main_item.base_item.num
                                    tmp1.main_item.base_item.num = item_pool["item_num"]
                                    rsp.items.add().CopyFrom(tmp1)
                                    tmp1.main_item.base_item.num = (
                                        num_t + item_pool["item_num"]
                                    )
                                    rsp1.items.add().CopyFrom(
                                        tmp1
                                    )  # TODO 目前是直接给礼包，不会自动开启
                                    db.set_item_detail(
                                        session.player_id,
                                        tmp1.SerializeToString(),
                                        item_pool["item_i_d"],
                                        None,
                                    )

        session.send(MsgId.ShopBuyRsp, rsp, packet_id)
        session.send(MsgId.PackNotice, rsp1, 0)
