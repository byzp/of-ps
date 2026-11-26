import random

from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import GachaReq, GachaRsp, ItemDetail, PackNotice, StatusCode
import utils.db as db
from utils import achieve_track, item_mgr
from utils.pb_create import make_item
from utils.res_loader import res


def _rows(sheet, table):
    section = res.get(sheet, {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def _configuration(gacha_id):
    info = next((row for row in _rows("Gacha", "info") if row.get("i_d") == gacha_id), None)
    pool = next((row for row in _rows("Gacha", "pool") if row.get("i_d") == gacha_id), None)
    if not info or not pool:
        return None
    pool_ids = {item["free_gacha_pool_i_d"] for item in pool.get("items", ())}
    guarantee_id = int(info.get("big_guarantee_pool_i_d", 0) or 0)
    normal = []
    guarantee = []
    reward_rows = _rows("Gacha", "reward_pool")
    for reward_pool_id in pool_ids:
        row = next((row for row in reward_rows if row.get("i_d") == reward_pool_id), None)
        items = [item["item_i_d"] for item in (row or {}).get("items", ()) if item.get("item_i_d")]
        if not items:
            return None
        normal.extend(items)
    if guarantee_id:
        row = next((row for row in reward_rows if row.get("i_d") == guarantee_id), None)
        guarantee = [item["item_i_d"] for item in (row or {}).get("items", ()) if item.get("item_i_d")]
        if not guarantee:
            return None
    if not normal:
        return None
    try:
        for item_id in normal + guarantee:
            item_mgr.validate_item_id(item_id)
    except item_mgr.EconomyConfigError:
        return None
    return info, normal, guarantee


def _cost(info, single):
    if single:
        count = item_mgr.checked_mul(
            int(info.get("method1_count", 0) or 0),
            int(info.get("consume_item1_num", 1) or 1),
        )
        return int(info.get("consume_item1_i_d", 0) or 0), count
    return int(info.get("consume_item2_i_d", 0) or 0), int(info.get("consume_item2_num", 0) or 0)


_QUALITY = None


def _quality_of(item_id):
    """物品品质：3=紫(SR) 4=金(SSR)，取 Item 表配置。"""
    global _QUALITY
    if _QUALITY is None:
        _QUALITY = {
            e.get("i_d"): int(e.get("quality", 0) or 0)
            for e in res["Item"]["item"]["datas"]
            if isinstance(e, dict)
        }
    return _QUALITY.get(item_id, 0)


@packet_handler(MsgId.GachaReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GachaReq()
        req.ParseFromString(data)
        configuration = _configuration(req.gacha_id)
        if configuration is None:
            session.send(MsgId.GachaRsp, GachaRsp(status=StatusCode.StatusCode_CFG_NOT_FOUND), packet_id)
            return
        info, normal, guarantee = configuration
        try:
            cost_id, cost_count = _cost(info, req.is_single)
            if not cost_id or cost_count <= 0:
                raise item_mgr.EconomyConfigError("invalid gacha cost")
            item_mgr.validate_stackable_item_id(cost_id)
            draws = 1 if req.is_single else 10
            cap = item_mgr.validate_counter(
                int(info.get("max_times", 70) or 70), allow_zero=False, label="gacha cap"
            )
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            session.send(MsgId.GachaRsp, GachaRsp(status=StatusCode.StatusCode_CFG_NOT_FOUND), packet_id)
            return

        rsp = GachaRsp(status=StatusCode.StatusCode_OK)
        rsp.info.gacha_id = req.gacha_id
        rsp.info.gacha_times = draws
        pack = PackNotice(status=StatusCode.StatusCode_OK)
        try:
            with item_mgr.player_lock(session.player_id), db.transaction():
                counter = item_mgr.validate_counter(
                    db.get_gacha_guarantee(session.player_id, req.gacha_id),
                    label="gacha guarantee",
                )
                rewards = []
                for index in range(draws):
                    if guarantee and counter + 1 >= cap:
                        reward = random.choice(guarantee)
                        counter = 0
                    else:
                        reward = random.choice(normal)
                        counter = item_mgr.checked_add(
                            counter, 1, limit=Config.ECONOMY_UINT32_MAX
                        )
                    if (
                        not Config.SKIP_QUESTS
                        and req.gacha_id == 2000
                        and req.is_single
                        and db.get_total_gacha_num(session.player_id, 2000) == 0
                    ):
                        reward = 102001
                    rewards.append(reward)
                item_mgr.validate_rewards([(reward, 1) for reward in rewards])
                if not item_mgr.consume_items(
                    session.player_id,
                    [(cost_id, cost_count)],
                    pack_notice=pack,
                    session=session,
                ):
                    rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
                else:
                    for reward in rewards:
                        self._grant(session, reward, rsp, pack)
                        db.add_gacha_record(session.player_id, req.gacha_id, reward)
                    db.set_gacha_guarantee(session.player_id, req.gacha_id, counter)
                    if guarantee:
                        rsp.info.guarantee = max(0, cap - counter)
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.items[:]
            del pack.items[:]

        session.send(MsgId.GachaRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
        achieve_track.report(session, "gacha", amount=draws)

    @staticmethod
    def _grant(session, reward, rsp, pack):
        character_cfg = next(
            (row for row in _rows("Character", "character") if row.get("i_d") == reward),
            None,
        )
        if character_cfg:
            item = rsp.items.add()
            duplicate = item_mgr.grant_character(session.player_id, reward, item, pack_notice=pack)
            if not duplicate:
                extra = ItemDetail()
                make_item(107, 500, session.player_id, extra)
                item.extras.add().CopyFrom(extra.main_item)
                item_mgr.grant_items(session.player_id, [(107, 500)], pack_notice=pack, session=session)
            item.extra_quality = int(character_cfg.get("quality", 0) or 0)
            pack.items.add().CopyFrom(item)
        else:
            item_mgr.grant_single_item(session.player_id, reward, num=1, rsp_items=rsp.items, pack_notice=pack)
