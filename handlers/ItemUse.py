import pickle
import random
import time

from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId
from proto.net_pb2 import (
    EBagItemTag,
    ItemUseReq,
    ItemUseRsp,
    PackNotice,
    PlayerBuffNotice as _PBN,
    StatusCode,
)
import utils.db as db
from utils import achieve_track, item_mgr
from utils.res_loader import res


def _rows(sheet, table):
    section = res.get(sheet, {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def _rewards(item_id):
    pool = next((row for row in _rows("Reward", "reward_pool") if row.get("i_d") == item_id), None)
    if pool is None:
        return []
    group_ids = [group.get("reward_pool_group_i_d") for group in pool.get("reward_pool_group", ())]
    if not group_ids:
        raise item_mgr.EconomyConfigError("empty item-use reward pool")
    item_pools = {row.get("i_d"): row for row in _rows("Reward", "reward_item_pool")}
    rewards = []
    for group_id in group_ids:
        item_pool = item_pools.get(group_id)
        if item_pool is None:
            raise item_mgr.EconomyConfigError("missing item-use reward group")
        for entry in item_pool.get("reward_item_pool_group", ()):
            minimum = int(entry.get("item_min_count", 1))
            maximum = int(entry.get("item_max_count", minimum))
            item_mgr.validate_count(minimum, label="reward minimum")
            item_mgr.validate_count(maximum, label="reward maximum")
            if minimum > maximum:
                raise item_mgr.EconomyConfigError("invalid reward count range")
            item_mgr.validate_item_id(entry.get("item_i_d"))
            rewards.append((entry["item_i_d"], random.randint(minimum, maximum)))
    item_mgr.validate_rewards(rewards)
    return rewards


@packet_handler(MsgId.ItemUseReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with achieve_track.batch(session):
            self._handle(session, data, packet_id)

    def _handle(self, session, data, packet_id):
        req = ItemUseReq()
        req.ParseFromString(data)
        rsp = ItemUseRsp()
        rsp.dungeon_id = session.dungeon[0] if session.dungeon else 0
        if req.num <= 0 or req.choose_item_id:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.ItemUseRsp, rsp, packet_id)
            return
        try:
            item_mgr.validate_count(req.num)
            item_row = item_mgr.validate_stackable_item_id(req.item_id)
            tag = item_row.get("new_bag_item_tag")
            buff = None
            if tag == EBagItemTag.EBagItemTag_Food:
                affect = next(
                    (row for row in _rows("Cooking", "cook_affect") if row.get("i_d") == req.item_id),
                    None,
                )
                if affect and affect.get("buff_i_d"):
                    duration = int(affect.get("food_effect_type_param", 0) or 0)
                    item_mgr.validate_counter(affect["buff_i_d"], allow_zero=False, label="food buff id")
                    item_mgr.validate_count(duration, label="food buff duration")
                    buff = (int(affect["buff_i_d"]), int(time.time()) + duration)
            restore = None
            if tag in (32, 35):
                restore_item = 10 if tag == 32 else 11
                relate = int(item_row.get("relate_i_d", 0) or 0)
                item_mgr.validate_stackable_item_id(restore_item)
                item_mgr.validate_count(relate, label="restore amount")
                restore = (restore_item, item_mgr.checked_mul(relate, req.num))
            catcher = next(
                (
                    row for row in _rows("Expression", "catcher")
                    if row.get("need_item_i_d") == req.item_id
                ),
                None,
            )
            if catcher:
                item_mgr.validate_counter(catcher.get("action_i_d", 0), allow_zero=False, label="action id")
            rewards = _rewards(req.item_id)
            if restore:
                rewards.append(restore)
            item_mgr.validate_rewards(rewards)
        except (item_mgr.EconomyConfigError, TypeError, ValueError):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.ItemUseRsp, rsp, packet_id)
            return

        pack = PackNotice(status=StatusCode.StatusCode_OK)
        with (
            item_mgr.player_lock(session.player_id),
            item_mgr.deferred_notifications(),
            db.transaction(),
        ):
            if not item_mgr.consume_items(
                session.player_id,
                [(req.item_id, req.num)],
                pack_notice=pack,
                session=session,
            ):
                rsp.status = StatusCode.StatusCode_ITEM_NOT_ENOUGH
            else:
                if buff:
                    buff_id, end = buff
                    raw = db.get_kv(session.player_id, "buffs", "life", b"")
                    store = pickle.loads(raw) if raw else {}
                    store[buff_id] = max(end, int(store.get(buff_id, 0)))
                    db.set_kv(session.player_id, "buffs", "life", pickle.dumps(store))
                if catcher:
                    expire_ms = int((time.time() + 24 * 3600) * 1000)
                    raw = db.get_kv(session.player_id, "actions", "ids", b"")
                    actions = {}
                    for pair in raw.decode().split(","):
                        if ":" in pair:
                            action_id, expiry = pair.split(":", 1)
                            actions[int(action_id)] = int(expiry)
                    action_id = int(catcher["action_i_d"])
                    actions[action_id] = max(actions.get(action_id, 0), expire_ms)
                    db.set_kv(
                        session.player_id,
                        "actions",
                        "ids",
                        ",".join(f"{key}:{value}" for key, value in actions.items()).encode(),
                    )
                if rewards:
                    item_mgr.grant_items(
                        session.player_id,
                        rewards,
                        pack_notice=pack,
                        rsp_items=rsp.items,
                        session=session,
                    )
                rsp.status = StatusCode.StatusCode_OK

        if rsp.status != StatusCode.StatusCode_OK:
            session.send(MsgId.ItemUseRsp, rsp, packet_id)
            return
        if tag == EBagItemTag.EBagItemTag_Food:
            achieve_track.report(session, "eat_food", amount=req.num)
            if buff:
                buff_id, end = buff
                notice = _PBN(status=StatusCode.StatusCode_OK)
                buff_entry = notice.player_buffs.add()
                buff_entry.system_type = 2
                entry = buff_entry.buff_lst.add()
                entry.buff_id = buff_id
                entry.end_time = end
                session.send(MsgId.PlayerBuffNotice, notice, 0)
        elif req.item_id == 10:
            achieve_track.report(session, "stamina_drink", amount=req.num)
        elif req.item_id == 11:
            achieve_track.report(session, "energy_drink", amount=req.num)
        if restore:
            achieve_track.report(
                session,
                "vitality_restore" if tag == 32 else "energy_restore",
                amount=req.num,
            )
        if catcher:
            achieve_track.report(session, "use_interact_item")
        session.send(MsgId.ItemUseRsp, rsp, packet_id)
        if pack.items:
            session.send(MsgId.PackNotice, pack, 0)
