from config import Config
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import ShopBuyReq, ShopBuyRsp, PackNotice, StatusCode

import utils.db as db
from utils import achieve_track, item_mgr, shop_state
from utils.res_loader import res
from utils.reward_resolver import resolve_reward


def _rows(sheet, table):
    section = res.get(sheet, {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def _price(currency, bought, buy_times):
    price = currency.get("price")
    ladder_id = currency.get("increasing_i_d")
    if ladder_id:
        ladder = next(
            (row for row in _rows("Shop", "increasing") if row.get("i_d") == ladder_id),
            None,
        )
        entries = ladder.get("items", ()) if ladder else ()
        if not entries:
            raise item_mgr.EconomyConfigError("missing shop price ladder")
        price = entries[min(bought, len(entries) - 1)].get("price")
    item_mgr.validate_count(price, label="shop price")
    return item_mgr.checked_mul(price, buy_times)


@packet_handler(MsgId.ShopBuyReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = ShopBuyReq()
        req.ParseFromString(data)
        with shop_state.purchase_lock(session.player_id), achieve_track.batch(session):
            self._buy(session, req, packet_id)

    def _buy(self, session, req, packet_id):
        rsp = ShopBuyRsp(status=StatusCode.StatusCode_OK, shop_id=req.shop_id)
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        if req.buy_times <= 0 or req.buy_times > Config.MAX_SHOP_BUY_TIMES:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ShopBuyRsp, rsp, packet_id)
            return

        try:
            with item_mgr.player_lock(session.player_id), db.transaction():
                level_row = db.get_players_info(session.player_id, "level")
                player_level = int(level_row[0] or 0) if level_row else 0
                grids = shop_state.grid_rows(req.shop_id)
                if grids is None:
                    rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                else:
                    grid = next(
                        (row for row in grids if row.get("grid_i_d") == req.grid_id),
                        None,
                    )
                    if grid is None:
                        rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                    else:
                        self._purchase(
                            session, req, grid, player_level, rsp, pack
                        )
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.items[:]
            del pack.items[:]

        session.send(MsgId.ShopBuyRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            if pack.items:
                session.send(MsgId.PackNotice, pack, 0)
        return

    @staticmethod
    def _purchase(session, req, grid, player_level, rsp, pack):
        bought = item_mgr.validate_counter(
            shop_state.buy_times(session.player_id, grid), label="shop purchases"
        )
        max_count = int(grid.get("buy_max_count", -1))
        if max_count < -1:
            raise item_mgr.EconomyConfigError("invalid shop purchase limit")
        if max_count >= 0:
            item_mgr.validate_counter(max_count, allow_zero=True, label="shop limit")
            new_count = item_mgr.checked_add(
                bought, req.buy_times, limit=Config.ECONOMY_UINT32_MAX
            )
            if new_count > max_count:
                rsp.status = StatusCode.StatusCode_SHOP_GRID_BUY_NUM_LIMIT
                return
        else:
            new_count = item_mgr.checked_add(
                bought, req.buy_times, limit=Config.ECONOMY_UINT32_MAX
            )

        pool_id = grid["shop_pool_i_d"]
        if grid.get("first_buy_shop_pool_i_d") and bought == 0:
            pool_id = grid["first_buy_shop_pool_i_d"]
        pool = next(
            (row for row in _rows("Shop", "pool") if row.get("i_d") == pool_id),
            None,
        )
        if pool is None:
            raise item_mgr.EconomyConfigError("missing shop pool")
        pool_index = int(grid.get("pool_index", 1))
        candidates = [
            row
            for row in pool.get("items", ())
            if int(row.get("index", 1)) == pool_index
            and (not req.item_id or row.get("item_i_d") == req.item_id)
        ]
        if len(candidates) != 1:
            raise item_mgr.EconomyConfigError("missing or ambiguous shop product")
        product = candidates[0]
        item_id = product.get("item_i_d")
        item_mgr.validate_item_id(item_id)
        item_num = int(product.get("item_num", 1))
        item_mgr.validate_count(item_num, label="shop item count")
        reward_count = item_mgr.checked_mul(item_num, req.buy_times)

        costs = {}
        for currency in product.get("shop_currency_item") or ():
            currency_id = int(currency.get("currency_i_d", 101))
            item_mgr.validate_stackable_item_id(currency_id)
            amount = _price(currency, bought, req.buy_times)
            if currency_id == 102:
                # 星石不足时用菱石(108)补差, 两种货币作为同一原子成本。
                have_star = item_mgr.get_num(session.player_id, 102)
                premium = max(0, amount - have_star)
                if have_star:
                    costs[102] = item_mgr.checked_add(costs.get(102, 0), have_star)
                if premium:
                    costs[108] = item_mgr.checked_add(costs.get(108, 0), premium)
            else:
                costs[currency_id] = item_mgr.checked_add(
                    costs.get(currency_id, 0), amount
                )
        cost_list = tuple((item_id, amount) for item_id, amount in costs.items() if amount)
        item_row = item_mgr.item_config(item_id)
        rewards = [(item_id, reward_count)]
        if item_row.get("new_bag_item_tag") == 1:
            expanded = resolve_reward(item_id, player_level)
            if expanded:
                rewards = [
                    (reward_id, item_mgr.checked_mul(count, req.buy_times))
                    for reward_id, count in expanded
                ]
        item_mgr.validate_rewards(rewards)

        if not item_mgr.consume_items(
            session.player_id, cost_list, pack_notice=pack, session=session
        ):
            rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            return
        db.set_kv(
            session.player_id, "shop_buy", shop_state.limit_key(grid), new_count
        )
        item_mgr.grant_items(
            session.player_id,
            rewards,
            rsp_items=rsp.items,
            pack_notice=pack,
            session=session,
        )
        for currency_id in costs:
            if currency_id in (102, 109):
                achieve_track.report(session, "shop_collect_buy", match=currency_id)
        rsp.status = StatusCode.StatusCode_OK
        rsp.grids.id = req.shop_id
        rsp.grids.grid_id = req.grid_id
        rsp.grids.pool_id = pool_id
        rsp.grids.pool_index = pool_index
        rsp.grids.buy_times = new_count
