"""可堆叠物品按玩家粒度加锁的统一收支入口。"""

from config import Config

import logging
import threading
from contextlib import contextmanager
from contextvars import ContextVar

from proto.net_pb2 import (
    Character,
    EBagItemTag,
    ItemDetail,
    PackNotice,
    PlayerUnlockFunctionNotice,
    PlayerLevelExpNotice,
    PlayerAbilityUnlockNotice,
    StatusCode,
)
from network.msg_id import MsgId

import utils.db as db
from utils import achieve_track
from utils.pb_create import make_item
from utils.res_loader import res

logger = logging.getLogger(__name__)

_locks = {}  # player_id -> threading.RLock
_notification_queue = ContextVar("item_mgr_notification_queue", default=None)


class EconomyConfigError(ValueError):
    """经济配置缺失或非法; 调用方必须拒绝本次请求。"""


@contextmanager
def deferred_notifications():
    """把通知延后到最外层经济事务成功提交之后。

    未配合显式事务使用时退化为立即执行, 保持其它调用方的既有行为。
    回调异常不会回滚已经提交的物品收支。
    """
    current = _notification_queue.get()
    pending = []
    token = _notification_queue.set(pending)
    try:
        yield
    except BaseException:
        pending.clear()
        raise
    finally:
        _notification_queue.reset(token)
    if current is None:
        for callback in pending:
            callback()
    else:
        current.extend(pending)


def _notify(callback):
    pending = _notification_queue.get()
    if pending is None:
        callback()
    else:
        pending.append(callback)


def player_lock(player_id):
    """该玩家的物品读改写锁; 特殊收支(如封顶发放)自行 with 后直读 db"""
    return _locks.setdefault(player_id, threading.RLock())


def _resource_rows(sheet, table):
    section = res.get(sheet, {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return rows if isinstance(rows, (list, tuple)) else ()


def item_config(item_id):
    """返回权威 Item 配置; 不存在时拒绝, 不构造虚构物品。"""
    if isinstance(item_id, bool) or not isinstance(item_id, int):
        raise EconomyConfigError("item id must be an integer")
    if not 0 < item_id <= Config.ECONOMY_UINT32_MAX:
        raise EconomyConfigError("item id is outside uint32")
    row = next(
        (row for row in _resource_rows("Item", "item") if row.get("i_d") == item_id),
        None,
    )
    if row is None:
        raise EconomyConfigError(f"missing Item config: {item_id}")
    return row


def character_config(item_id):
    try:
        item_config(item_id)
    except EconomyConfigError:
        pass
    row = next(
        (
            row
            for row in _resource_rows("Character", "character")
            if row.get("i_d") == item_id
        ),
        None,
    )
    if row is None:
        raise EconomyConfigError(f"missing Character config: {item_id}")
    return row


def validate_item_id(item_id):
    """物品或角色均可发放, 但必须在权威表中存在。"""
    try:
        return item_config(item_id)
    except EconomyConfigError:
        return character_config(item_id)


def validate_stackable_item_id(item_id):
    row = item_config(item_id)
    if row.get("new_bag_item_tag") in Config.ITEM_MGR_INSTANCE_TAGS:
        raise EconomyConfigError(f"item is not stackable: {item_id}")
    if _is_character_item(item_id):
        raise EconomyConfigError(f"character is not stackable: {item_id}")
    return row


def validate_count(num, *, allow_zero=False, label="item count"):
    if isinstance(num, bool) or not isinstance(num, int):
        raise EconomyConfigError(f"{label} must be an integer")
    if num < 0 or (num == 0 and not allow_zero):
        raise EconomyConfigError(f"{label} must be positive")
    if num > Config.ECONOMY_ITEM_NUM_MAX:
        raise EconomyConfigError(f"{label} is outside int64")
    return num


def validate_counter(value, *, allow_zero=True, label="counter"):
    validate_count(value, allow_zero=allow_zero, label=label)
    if value > Config.ECONOMY_UINT32_MAX:
        raise EconomyConfigError(f"{label} is outside uint32")
    return value


def checked_add(left, right, *, limit=None):
    validate_count(left, allow_zero=True, label="stored amount")
    validate_count(right, label="delta")
    result = left + right
    if result > (Config.ECONOMY_ITEM_NUM_MAX if limit is None else limit):
        raise EconomyConfigError("economy amount overflow")
    return result


def checked_mul(left, right, *, limit=None):
    validate_count(left, label="multiplier")
    validate_count(right, label="multiplicand")
    result = left * right
    if result > (Config.ECONOMY_ITEM_NUM_MAX if limit is None else limit):
        raise EconomyConfigError("economy multiplication overflow")
    return result


def validate_rewards(reward_list):
    """在任何写库前验证整批奖励; 0 数量无副作用, 负数/未知物品拒绝。"""
    validated = []
    for entry in reward_list:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise EconomyConfigError("reward must be (item_id, count)")
        item_id, num = entry
        validate_item_id(item_id)
        validate_count(num, allow_zero=True)
        if num == 0:
            continue
        row = item_config(item_id) if not _is_character_item(item_id) else None
        if row and row.get("new_bag_item_tag") in Config.ITEM_MGR_INSTANCE_TAGS:
            if num > Config.ECONOMY_MAX_INSTANCE_GRANT:
                raise EconomyConfigError("too many instance rewards")
        if _is_character_item(item_id):
            cfg = character_config(item_id)
            repeat_id = int(cfg.get("repeat_item_i_d", 0) or 0)
            validate_stackable_item_id(repeat_id)
            if num != 1:
                raise EconomyConfigError("character reward count must be one")
        validated.append((item_id, num))
    return tuple(validated)


@contextmanager
def _player_transaction(player_id):
    """玩家锁 → DB transaction; 已持有同一 RLock 时只嵌套事务。"""
    lock = player_lock(player_id)
    owned = False
    try:
        owned = isinstance(lock, type(threading.RLock())) and lock._is_owned()
    except AttributeError:
        pass
    if owned:
        with db.transaction():
            yield
    else:
        with lock, db.transaction():
            yield


def _load(player_id, item_id):
    """锁内使用: 读取或按权威配置构造 ItemDetail。"""
    validate_stackable_item_id(item_id)
    detail = ItemDetail()
    raw = db.get_item_detail(player_id, item_id)
    if raw:
        detail.ParseFromString(raw)
    else:
        made = make_item(item_id, 0, player_id, detail)
        if not isinstance(made, ItemDetail) or detail.main_item.item_id != item_id:
            raise EconomyConfigError(f"cannot construct Item config: {item_id}")
        if detail.main_item.WhichOneof("item") != "base_item":
            raise EconomyConfigError(f"item is not stackable: {item_id}")
    if detail.main_item.WhichOneof("item") != "base_item":
        raise EconomyConfigError(f"stored item is not stackable: {item_id}")
    validate_count(detail.main_item.base_item.num, allow_zero=True)
    mark_new_item(player_id, detail)
    return detail


def get_num(player_id, item_id):
    """当前持有数量。"""
    validate_stackable_item_id(item_id)
    with player_lock(player_id):
        raw = db.get_item_detail(player_id, item_id)
        if not raw:
            return 0
        detail = ItemDetail()
        detail.ParseFromString(raw)
        if detail.main_item.WhichOneof("item") != "base_item":
            raise EconomyConfigError(f"stored item is not stackable: {item_id}")
        num = detail.main_item.base_item.num
        validate_count(num, allow_zero=True, label="stored amount")
        return num


def grant_character(player_id, char_id, item, pack_notice=None) -> bool:
    """获得角色; 重复角色严格按 repeat_item_i_d 转换, 无配置回退。"""
    cfg = character_config(char_id)
    repeat_id = int(cfg.get("repeat_item_i_d", 0) or 0)
    validate_stackable_item_id(repeat_id)
    with _player_transaction(player_id):
        _mark_got(player_id, char_id)
        owned = any(
            Character.FromString(blob).character_id == char_id
            for blob in db.get_characters(player_id)
        )
        if not owned:
            known_items = set(db.get_claimed(player_id, "got_ids"))
            item.main_item.item_id = char_id
            item.main_item.item_tag = EBagItemTag.EBagItemTag_Card
            db.add_character(player_id, char_id, item.main_item.character)
            if item.main_item.character.character_id != char_id:
                raise EconomyConfigError(f"cannot construct Character config: {char_id}")
            item.main_item.is_new = True
            if pack_notice is not None:
                _append_character_default_items(
                    player_id, item.main_item.character, pack_notice, known_items
                )
            return False

        item.CopyFrom(grant_single_item(player_id, repeat_id, 1))
        return True


_item_tags = None


def _tag_of(item_id):
    global _item_tags
    if _item_tags is None:
        rows = res.get("Item", {}).get("item", {}).get("datas", ())
        _item_tags = {
            e.get("i_d"): e.get("new_bag_item_tag")
            for e in rows
            if isinstance(e, dict)
        } if isinstance(rows, (list, tuple)) else {}
    return _item_tags.get(item_id)


_character_ids = None

_player_unlock_item_ids = None


def _unlock_item_ids():
    """PlayerUnlock 中作为背包道具发放的 id。"""
    global _player_unlock_item_ids
    if _player_unlock_item_ids is None:
        rows = _resource_rows("PlayerUnlock", "player_unlock")
        _player_unlock_item_ids = {
            row["item_i_d"]
            for row in rows
            if isinstance(row, dict) and row.get("item_i_d")
        }
    return _player_unlock_item_ids


def _is_character_item(item_id) -> bool:
    """角色 id 判定(Character.character 表存在该行): 官方对角色类奖励
    (如签到第7天 401001)下发完整 character 块, 不能按普通物品叠加。"""
    global _character_ids
    if _character_ids is None:
        _character_ids = {
            e.get("i_d")
            for e in res.get("Character", {}).get("character", {}).get("datas", ())
        }
    return _tag_of(item_id) == Config.ITEM_MGR_CARD_TAG and item_id in _character_ids


def _is_instance(detail: ItemDetail) -> bool:
    which = detail.main_item.WhichOneof("item")
    if not which:
        return False
    sub = getattr(detail.main_item, which)
    return hasattr(sub, "instance_id") and bool(sub.instance_id)


def _mark_got(player_id, item_id):
    """历史获得登记(ns=got_ids): 官方收藏界面为"曾获得过"(消耗后仍计),
    背包推导会随消耗丢失。insert-or-ignore 幂等, 天然并发安全。"""
    if not item_id:
        return False
    return db.try_claim(player_id, "got_ids", str(item_id))


def mark_new_item(player_id, detail):
    """按物品模板的历史获得记录标记本次首获，不按库存余量或实例号判断。"""
    detail.main_item.is_new = _mark_got(player_id, detail.main_item.item_id)


def _append_character_default_items(player_id, character, pack_notice, known_items):
    """把新角色创建时同时生成的默认装备/时装同步到 PackNotice。"""
    entries = []

    def _add_entry(item_id=None, instance_id=None):
        if not item_id and not instance_id:
            return
        entry = (item_id, instance_id)
        if entry not in entries:
            entries.append(entry)

    equipment = character.equipment_presets[0] if character.equipment_presets else None
    if equipment is not None:
        _add_entry(instance_id=equipment.weapon)
        for armor in equipment.armors:
            _add_entry(instance_id=armor.armor_id)
        for poster in equipment.posters:
            _add_entry(instance_id=poster.poster_id)

    outfit = character.outfit_presets[0] if character.outfit_presets else None
    if outfit is not None:
        for item_id in (
            outfit.clothes,
            outfit.ornament,
            outfit.hat,
            outfit.hair,
            outfit.pend_top,
            outfit.pend_chest,
            outfit.pend_pelvis,
            outfit.pend_up_face,
            outfit.pend_down_face,
            outfit.pend_left_hand,
            outfit.pend_right_hand,
            outfit.pend_left_foot,
            outfit.pend_right_foot,
        ):
            _add_entry(item_id=item_id)

    for item_id, instance_id in entries:
        blob = (
            db.get_item_detail(player_id, item_id)
            if item_id
            else db.get_item_detail(player_id, None, instance_id)
        )
        if not blob:
            continue
        detail = ItemDetail()
        detail.ParseFromString(blob)
        key = str(detail.main_item.item_id)
        detail.main_item.is_new = key not in known_items
        known_items.add(key)
        pack_notice.items.add().CopyFrom(detail)


def grant_single_item(player_id, item_id, num=1, pack_notice=None, rsp_items=None):
    """安全发放入口: 堆叠物品累加, 实例物品逐件分配并落库。"""
    validate_count(num)
    row = validate_item_id(item_id)
    if _is_character_item(item_id):
        raise EconomyConfigError("character rewards must use grant_character")
    if row.get("new_bag_item_tag") in Config.ITEM_MGR_INSTANCE_TAGS and num != 1:
        raise EconomyConfigError("instance reward count must be one")
    detail = ItemDetail()
    with _player_transaction(player_id):
        raw = db.get_item_detail(player_id, item_id)
        if raw:
            detail.ParseFromString(raw)
            if detail.main_item.WhichOneof("item") != "base_item":
                # 唯一物品（时装/铭文/收藏卡等）已持有：幂等返回，不再生成第二件。
                return detail
            validate_count(detail.main_item.base_item.num, allow_zero=True)
        gained_new = _mark_got(player_id, item_id)
        if raw:
            detail.main_item.base_item.num = checked_add(
                detail.main_item.base_item.num, num
            )
            detail.main_item.is_new = gained_new
            db.set_item_detail(player_id, detail.SerializeToString(), item_id, None)
        else:
            made = make_item(item_id, num, player_id, detail)
            if not isinstance(made, ItemDetail) or detail.main_item.item_id != item_id:
                raise EconomyConfigError(f"cannot construct Item config: {item_id}")
            detail.main_item.is_new = gained_new
            which = detail.main_item.WhichOneof("item")
            if which and _is_instance(detail):
                db.set_item_detail(
                    player_id,
                    detail.SerializeToString(),
                    None,
                    getattr(detail.main_item, which).instance_id,
                )
            elif which in ("base_item", "outfit", "inscription", "character"):
                db.set_item_detail(player_id, detail.SerializeToString(), item_id, None)
            else:
                raise EconomyConfigError(f"unsupported Item config: {item_id}")

    if rsp_items is not None or pack_notice is not None:
        if rsp_items is not None:
            show = ItemDetail()
            show.CopyFrom(detail)
            if detail.main_item.WhichOneof("item") == "base_item":
                show.main_item.base_item.num = num
            show.main_item.is_new = gained_new
            rsp_items.add().CopyFrom(show)
        if pack_notice is not None:
            total = ItemDetail()
            total.CopyFrom(detail)
            total.main_item.is_new = gained_new
            pack_notice.items.add().CopyFrom(total)
    return detail


_character_ids = None


def grant_items(
    player_id,
    reward_list,
    rsp_items=None,
    pack_notice=None,
    session=None,
    unlock_function_ids=None,
):
    """原子发放 [(item_id, num), ...]; 整批配置和数量先验证再写库。"""
    rewards = validate_rewards(tuple(reward_list or ()))
    totals = []
    if not rewards:
        return totals
    unlock_order = None
    if unlock_function_ids is None:
        unlock_candidates = _unlock_item_ids()
    else:
        unlock_order = tuple(dict.fromkeys(unlock_function_ids))
        unlock_candidates = set(unlock_order)
    unlock_ids = []
    auto_notice = None
    if pack_notice is None and session is not None:
        auto_notice = PackNotice()
        auto_notice.status = StatusCode.StatusCode_OK
        pack_notice = auto_notice
    level_exp = None
    new_abilities = []
    new_unlocks = []
    with _player_transaction(player_id):
        stackables = []
        for item_id, num in rewards:
            if item_id in unlock_candidates and item_id not in unlock_ids:
                unlock_ids.append(item_id)
            if _is_character_item(item_id):
                det = ItemDetail()
                grant_character(player_id, item_id, det, pack_notice=pack_notice)
                totals.append(det)
                if rsp_items is not None:
                    rsp_items.add().CopyFrom(det)
                if pack_notice is not None:
                    pack_notice.items.add().CopyFrom(det)
            elif _tag_of(item_id) in Config.ITEM_MGR_INSTANCE_TAGS:
                for _ in range(num):
                    totals.append(
                        grant_single_item(
                            player_id,
                            item_id,
                            1,
                            pack_notice=pack_notice,
                            rsp_items=rsp_items,
                        )
                    )
            elif _tag_of(item_id) in Config.ITEM_MGR_UNIQUE_TAGS:
                # 唯一物品按 item_id 持有，重复奖励幂等，不按堆叠数量累加。
                totals.append(
                    grant_single_item(
                        player_id,
                        item_id,
                        1,
                        pack_notice=pack_notice,
                        rsp_items=rsp_items,
                    )
                )
            else:
                stackables.append((item_id, num))
        ability_ids = {
            row["need_item_i_d"]: row["i_d"]
            for row in _resource_rows("Ability", "ability")
            if row.get("need_item_i_d")
        }
        for item_id, num in stackables:
            if item_id == 1 and session is not None:
                level_exp = db.add_player_exp(player_id, num)
            detail = _load(player_id, item_id)
            gained_new = detail.main_item.is_new
            ability_id = ability_ids.get(item_id)
            if ability_id and detail.main_item.base_item.num == 0:
                if db.get_kv(player_id, "ability", ability_id) is None:
                    db.set_kv(player_id, "ability", ability_id, 0)
                    new_abilities.append(ability_id)
            detail.main_item.base_item.num = checked_add(
                detail.main_item.base_item.num, num
            )
            db.set_item_detail(player_id, detail.SerializeToString(), item_id, None)
            totals.append(detail)
            if rsp_items is not None:
                gain = ItemDetail()
                gain.CopyFrom(detail)
                gain.main_item.base_item.num = num
                gain.main_item.is_new = gained_new
                rsp_items.add().CopyFrom(gain)
            if pack_notice is not None:
                pack_notice.items.add().CopyFrom(detail)
        if unlock_order is not None:
            unlock_ids = [
                function_id for function_id in unlock_order if function_id in unlock_ids
            ]
        if unlock_ids:
            new_unlocks = db.add_unlock_functions(player_id, unlock_ids)

    # 通知和成就只在数据库提交后执行, 不参与经济写入的回滚边界。
    if level_exp is not None:
        def level_notice(level_exp=level_exp):
            notice = PlayerLevelExpNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.level, notice.exp = level_exp
            session.send(MsgId.PlayerLevelExpNotice, notice, 0)
            achieve_track.report(session, "player_level", level=level_exp[0])
        _notify(level_notice)
    if session is not None:
        for item_id, num in rewards:
            _notify(lambda item_id=item_id, num=num: achieve_track.report(
                session, "gain_item", match=item_id, amount=num
            ))
    if session is not None and new_unlocks:
        def unlock_notices():
            for function_id in new_unlocks:
                unlock_notice = PlayerUnlockFunctionNotice()
                unlock_notice.status = StatusCode.StatusCode_OK
                unlock_notice.unlock_functions.append(function_id)
                session.send(MsgId.PlayerUnlockFunctionNotice, unlock_notice, 0)
        _notify(unlock_notices)
    if auto_notice is not None and auto_notice.items:
        _notify(lambda: session.send(MsgId.PackNotice, auto_notice, 0))
    if session is not None:
        def ability_notices():
            for ability_id in new_abilities:
                notice = PlayerAbilityUnlockNotice()
                notice.status = StatusCode.StatusCode_OK
                notice.ability_id = ability_id
                session.send(MsgId.PlayerAbilityUnlockNotice, notice, 0)
        _notify(ability_notices)
    return totals


def needs_temp_pack(detail):
    """世界掉落的装备实例和材料占临时背包；货币、衣装等直接到账。"""
    return (
        _is_instance(detail)
        or detail.main_item.item_tag == EBagItemTag.EBagItemTag_Material
    )


def validate_pickup_item(detail):
    """在领取去重或任何写库前验证掉落快照, 防止损坏/伪造物品入包。"""
    if not isinstance(detail, ItemDetail):
        raise EconomyConfigError("pickup item must be ItemDetail")
    item_id = detail.main_item.item_id
    row = validate_item_id(item_id)
    which = detail.main_item.WhichOneof("item")
    if not which:
        raise EconomyConfigError("pickup item has no payload")
    expected_tag = row.get("new_bag_item_tag")
    if expected_tag is not None and detail.main_item.item_tag != expected_tag:
        raise EconomyConfigError("pickup item tag does not match Item config")
    if which == "base_item":
        if detail.main_item.base_item.item_id != item_id:
            raise EconomyConfigError("pickup base item id mismatch")
        validate_count(detail.main_item.base_item.num, label="pickup item count")
    elif which in ("weapon", "armor", "poster", "treasure", "pet"):
        instance_id = getattr(detail.main_item, which).instance_id
        validate_counter(instance_id, allow_zero=False, label="pickup instance id")
    return detail


def pickup_rewards(
    session,
    items,
    rsp_items,
    pack_notice,
    to_inventory=False,
    *,
    staged_temp_pack=None,
    temp_pack_start=None,
):
    """保留掉落实例与属性，统一拾取同步；扫荡可直接入仓库。

    调用方必须持有玩家锁并处于 DB 事务中。传 staged_temp_pack 时只暂存
    会话态, 由调用方在事务提交后合并, 避免保存失败却留下可再次领取的标记。
    """
    if staged_temp_pack is None and temp_pack_start is None:
        temp_pack = session.temp_pack
    elif staged_temp_pack is not None:
        temp_pack = staged_temp_pack
    else:
        raise EconomyConfigError("staged pickup requires a staging list")
    start = len(session.temp_pack) if temp_pack_start is None else temp_pack_start
    validate_counter(start, label="temporary pack size")
    if start > Config.TEMP_PACK_MAX:
        raise EconomyConfigError("temporary pack size overflow")
    for source in items:
        validate_pickup_item(source)
    for source in items:
        item = ItemDetail()
        item.CopyFrom(source)
        item.pack_type = ItemDetail.PackType.PackType_Inventory
        instance_id = 0
        if _is_instance(item):
            which = item.main_item.WhichOneof("item")
            instance_id = getattr(item.main_item, which).instance_id
            if db.get_item_detail(session.player_id, None, instance_id):
                raise EconomyConfigError("pickup instance already exists")
            mark_new_item(session.player_id, item)
            db.set_item_detail(
                session.player_id, item.SerializeToString(), None, instance_id
            )
            _notify(lambda item_id=item.main_item.item_id: achieve_track.report(
                session, "gain_item", match=item_id
            ))
        else:
            count = (
                item.main_item.base_item.num
                if item.main_item.WhichOneof("item") == "base_item"
                else 1
            )
            if to_inventory or not needs_temp_pack(item):
                grant_items(
                    session.player_id,
                    [(item.main_item.item_id, count)],
                    rsp_items=rsp_items,
                    pack_notice=pack_notice,
                    session=session,
                )
                continue
            # 材料拾取时只累计一次正式库存; 临时包保存同一次获得的快照,
            # 入库/丢弃时转正或扣除, 不能再次 grant。
            totals = grant_items(
                session.player_id,
                [(item.main_item.item_id, count)],
                pack_notice=PackNotice(),
                session=session,
            )
            item.main_item.is_new = totals[0].main_item.is_new
        if to_inventory:
            rsp_items.add().CopyFrom(item)
            pack_notice.items.add().CopyFrom(item)
            continue
        if start + len(temp_pack) >= Config.TEMP_PACK_MAX:
            raise EconomyConfigError("temporary pack is full")
        item.pack_type = ItemDetail.PackType.PackType_TempPack
        item.main_item.temp_pack_index = start + len(temp_pack) + 1
        rsp_items.add().CopyFrom(item)
        pack_notice.items.add().CopyFrom(item)
        # 首获提示只属于本次拾取；排序、入库等临时包回放不再提示。
        item.main_item.is_new = False
        temp_pack.append((instance_id, item.SerializeToString()))


def consume_items(player_id, cost_list, pack_notice=None, session=None):
    """原子扣除 [(item_id, num), ...]; 同种合并, 任一不足则全部不扣。

    0 数量保留为内部无消耗语义; 负数、未知物品和溢出数量直接拒绝。
    """
    costs = tuple(cost_list or ())
    merged = {}
    for entry in costs:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise EconomyConfigError("cost must be (item_id, count)")
        item_id, num = entry
        validate_stackable_item_id(item_id)
        validate_count(num, allow_zero=True)
        if num:
            merged[item_id] = checked_add(merged.get(item_id, 0), num)
    if not merged:
        return True
    with _player_transaction(player_id):
        details = {}
        for item_id, need in merged.items():
            raw = db.get_item_detail(player_id, item_id)
            if not raw:
                return False
            detail = ItemDetail()
            detail.ParseFromString(raw)
            if detail.main_item.WhichOneof("item") != "base_item":
                raise EconomyConfigError(f"stored item is not stackable: {item_id}")
            current = detail.main_item.base_item.num
            validate_count(current, allow_zero=True, label="stored amount")
            if current < need:
                return False
            details[item_id] = detail
        for item_id, need in merged.items():
            detail = details[item_id]
            detail.main_item.is_new = False
            detail.main_item.base_item.num -= need
            db.set_item_detail(player_id, detail.SerializeToString(), item_id, None)
            if pack_notice is not None:
                pack_notice.items.add().CopyFrom(detail)
    if session is not None:
        for item_id, num in costs:
            if item_id == 101 and num > 0:
                _notify(lambda num=num: achieve_track.report(
                    session, "spend_coin", amount=num
                ))
    return True
