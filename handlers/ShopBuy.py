from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId


from proto.net_pb2 import (
    ShopBuyReq,
    ShopBuyRsp,
    ItemDetail,
    PackNotice,
    StatusCode,
)

import utils.db as db
from utils import item_mgr
from utils.res_loader import res
from utils.pb_create import make_item
from utils.reward_resolver import resolve_reward
from utils import achieve_track
from utils import shop_state


@packet_handler(MsgId.ShopBuyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ShopBuyReq()
        req.ParseFromString(data)

        with shop_state.purchase_lock(session.player_id), achieve_track.batch(session):
            self._buy(session, req, packet_id)

    def _buy(self, session, req, packet_id):

        player_level = int(db.get_players_info(session.player_id, "level")[0] or 0)

        rsp = ShopBuyRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.shop_id = req.shop_id
        pool_id_ok = 0
        pool_index_ok = 1
        new_buy_times = 0

        rsp1 = PackNotice()
        rsp1.status = StatusCode.StatusCode_OK
        _item_matched = False
        _grid_matched = False
        for data in res["Shop"]["grid"]["datas"]:
            if data["i_d"] == req.shop_id:
                _grid_matched = True
                for grid_cfg in shop_state.grid_rows(req.shop_id) or ():
                    if grid_cfg["grid_i_d"] == req.grid_id:
                        max_cnt = grid_cfg.get("buy_max_count", -1)
                        limit_key = shop_state.limit_key(grid_cfg)
                        bought = shop_state.buy_times(session.player_id, grid_cfg)
                        if 0 <= max_cnt < bought + req.buy_times:
                            rsp.status = StatusCode.StatusCode_FAIL
                            session.send(MsgId.ShopBuyRsp, rsp, packet_id)
                            return
                        # 首购特惠: 首次购买使用 first_buy_shop_pool_i_d
                        eff_pool_id = grid_cfg["shop_pool_i_d"]
                        pool_index_ok = grid_cfg.get("pool_index", 1)
                        if grid_cfg.get("first_buy_shop_pool_i_d") and bought == 0:
                            eff_pool_id = grid_cfg["first_buy_shop_pool_i_d"]
                        for pool in res["Shop"]["pool"]["datas"]:
                            if pool["i_d"] == eff_pool_id:
                                pool_id_ok = pool["i_d"]
                                for item_pool in pool["items"]:
                                    if item_pool.get("index", 1) != grid_cfg.get(
                                        "pool_index", 1
                                    ):
                                        continue
                                    # 多商品池: 客户端指定 item_id 时仅购买该商品
                                    if (
                                        req.item_id
                                        and item_pool.get("item_i_d") != req.item_id
                                    ):
                                        continue
                                    _item_matched = True
                                    cur_use = {}
                                    currencies = (
                                        item_pool.get("shop_currency_item") or ()
                                    )
                                    for currency in currencies:
                                        # 缺省货币为金币(Shop 表部分条目无 currency_i_d)
                                        currency_id = currency.get("currency_i_d", 101)
                                        _inc_id = currency.get("increasing_i_d")
                                        if _inc_id:
                                            _ladder = next(
                                                (
                                                    r.get("items", ())
                                                    for r in res["Shop"]["increasing"][
                                                        "datas"
                                                    ]
                                                    if r.get("i_d") == _inc_id
                                                ),
                                                (),
                                            )
                                            if _ladder:
                                                _idx = min(
                                                    int(bought),
                                                    len(_ladder) - 1,
                                                )
                                                cur = (
                                                    int(_ladder[_idx].get("price", 0))
                                                    * req.buy_times
                                                )
                                            else:
                                                cur = currency["price"] * req.buy_times
                                        else:
                                            cur = currency["price"] * req.buy_times
                                        cur_t = db.get_item_detail(
                                            session.player_id, currency_id
                                        )
                                        cur_item = ItemDetail()
                                        if not cur_t:
                                            make_item(
                                                currency_id,
                                                0,
                                                session.player_id,
                                                cur_item,
                                            )
                                        else:
                                            cur_item.ParseFromString(cur_t)
                                        num = cur_item.main_item.base_item.num
                                        if (
                                            num < cur and currency_id == 102
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
                                        cur_use[currency_id] = cur_item
                                    # 没有 shop_currency_item 的格子是免费商品，
                                    # 例如 Shop 400/grid 1 的礼包 6020010。
                                    for k, v in cur_use.items():
                                        db.set_item_detail(
                                            session.player_id,
                                            v.SerializeToString(),
                                            k,
                                            None,
                                        )
                                        rsp1.items.add().CopyFrom(v)
                                        # 成就: 使用收集点购买(收集点货币 102/109)
                                        if k in (102, 109):
                                            achieve_track.report(
                                                session, "shop_collect_buy", match=k
                                            )
                                    db.set_kv(
                                        session.player_id,
                                        "shop_buy",
                                        limit_key,
                                        bought + req.buy_times,
                                    )
                                    new_buy_times = bought + req.buy_times
                                    _gift_item = item_pool["item_i_d"]
                                    _gift_tag = next(
                                        (
                                            e.get("new_bag_item_tag")
                                            for e in res["Item"]["item"]["datas"]
                                            if isinstance(e, dict)
                                            and e.get("i_d") == _gift_item
                                        ),
                                        0,
                                    )
                                    _expanded = (
                                        resolve_reward(_gift_item, player_level)
                                        if _gift_tag == 1
                                        else []
                                    )
                                    if _expanded:
                                        mult = []
                                        for _it, _n in _expanded:
                                            mult.append((_it, _n * req.buy_times))
                                        item_mgr.grant_items(
                                            session.player_id,
                                            mult,
                                            rsp_items=rsp.items,
                                            pack_notice=rsp1,
                                            session=session,
                                        )
                                        continue
                                    item_mgr.grant_items(
                                        session.player_id,
                                        [
                                            (
                                                item_pool["item_i_d"],
                                                item_pool.get("item_num", 1)
                                                * req.buy_times,
                                            )
                                        ],
                                        rsp_items=rsp.items,
                                        pack_notice=rsp1,
                                        session=session,
                                    )
        if req.item_id and not _item_matched:
            rsp.status = StatusCode.StatusCode_BAD_REQ
        if not _grid_matched:
            # 未找到对应商店网格: 拒绝而非静默成功
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
        if not _item_matched and rsp.status == StatusCode.StatusCode_OK:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
        if rsp.status == StatusCode.StatusCode_OK:
            rsp.grids.id = req.shop_id
            rsp.grids.grid_id = req.grid_id
            rsp.grids.pool_id = pool_id_ok
            rsp.grids.pool_index = pool_index_ok
            rsp.grids.buy_times = new_buy_times or req.buy_times
        session.send(MsgId.ShopBuyRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            session.send(MsgId.PackNotice, rsp1, 0)
