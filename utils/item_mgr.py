"""可堆叠物品按玩家粒度加锁的统一收支入口。"""

from config import Config

import logging
import threading

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

_locks = {}  # player_id -> threading.Lock


def player_lock(player_id):
    """该玩家的物品读改写锁; 特殊收支(如封顶发放)自行 with 后直读 db"""
    return _locks.setdefault(player_id, threading.Lock())


def _load(player_id, item_id):
    """锁内使用: 读出或构造 ItemDetail(带资源缺失兜底)"""
    detail = ItemDetail()
    raw = db.get_item_detail(player_id, item_id)
    if raw:
        detail.ParseFromString(raw)
    else:
        make_item(item_id, 0, player_id, detail)
        if detail.main_item.WhichOneof("item") is None:
            detail.main_item.item_id = item_id
            detail.main_item.base_item.item_id = item_id
    mark_new_item(player_id, detail)
    return detail


def get_num(player_id, item_id):
    """当前持有数量"""
    raw = db.get_item_detail(player_id, item_id)
    if not raw:
        return 0
    detail = ItemDetail()
    detail.ParseFromString(raw)
    return detail.main_item.base_item.num


def grant_character(player_id, char_id, item, pack_notice=None) -> bool:
    """获得角色: 未拥有则入库并填入 item(角色分支), 返回 False;
    已拥有则按 Character.repeat_item_i_d 转换为碎片填入 item, 返回 True。"""
    _mark_got(player_id, char_id)
    owned = False
    for blob in db.get_characters(player_id):
        c = Character()
        c.ParseFromString(blob)
        if c.character_id == char_id:
            owned = True
            break

    if not owned:
        known_items = set(db.get_claimed(player_id, "got_ids"))
        item.main_item.item_id = char_id
        item.main_item.item_tag = EBagItemTag.EBagItemTag_Card
        db.add_character(player_id, char_id, item.main_item.character)
        item.main_item.is_new = True
        if pack_notice is not None:
            _append_character_default_items(
                player_id, item.main_item.character, pack_notice, known_items
            )
        return False

    # 重复角色 → 碎片(Character.repeat_item_i_d), 缺配置回退金币101
    repeat = 0
    for e in res["Character"]["character"]["datas"]:
        if e.get("i_d") == char_id:
            repeat = int(e.get("repeat_item_i_d", 0) or 0)
            break
    item.CopyFrom(grant_single_item(player_id, repeat or 101, 1))
    return True


_item_tags = None


def _tag_of(item_id):
    global _item_tags
    if _item_tags is None:
        _item_tags = {
            e.get("i_d"): e.get("new_bag_item_tag")
            for e in res.get("Item", {}).get("item", {}).get("datas", ())
        }
    return _item_tags.get(item_id)


_character_ids = None

_player_unlock_item_ids = None


def _unlock_item_ids():
    """PlayerUnlock 中作为背包道具发放的 id。"""
    global _player_unlock_item_ids
    if _player_unlock_item_ids is None:
        rows = res["PlayerUnlock"]["player_unlock"]["datas"]
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
    """礼包/商店等奖励的安全发放入口:
    可堆叠物品合并入背包; 实例类(武器/映像/防具等)新分配 instance_id 单独落库。"""
    detail = ItemDetail()
    with player_lock(player_id):
        raw = db.get_item_detail(player_id, item_id)
        if raw:
            detail.ParseFromString(raw)
        gained_new = _mark_got(player_id, item_id)
        if raw and not _is_instance(detail):
            # 可堆叠: 数量合并
            if detail.main_item.WhichOneof("item") == "base_item":
                detail.main_item.base_item.num += num
            detail.main_item.is_new = gained_new
            db.set_item_detail(player_id, detail.SerializeToString(), item_id, None)
        else:
            make_item(item_id, num, player_id, detail)
            detail.main_item.is_new = gained_new
            which = detail.main_item.WhichOneof("item")
            if which and _is_instance(detail):
                db.set_item_detail(
                    player_id,
                    detail.SerializeToString(),
                    None,
                    getattr(detail.main_item, which).instance_id,
                )
            else:
                db.set_item_detail(player_id, detail.SerializeToString(), item_id, None)

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
    """发放 [(item_id, num), ...]。

    rsp_items:    Rsp 中的 repeated ItemDetail, 每条填 num=本次获得数量(展示用)
    pack_notice:  PackNotice, items 填叠加后的背包总量(同步背包用);
                  传 None 且给了 session 时自动构造并 session.send(PackNotice)
    session:      仅用于自动推送 PackNotice
    unlock_function_ids: None 表示按 reward_list 中的 PlayerUnlock 道具自动
                         开启功能；传入序列时只开启该序列(用于初始教程
                         奖励中同时存在“道具已发放但功能不新增”的条目)
    返回 [叠加后的 ItemDetail, ...]
    """
    totals = []
    if not reward_list:
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
    # 不可叠加条目先在锁外路由(grant_single_item 自带同把玩家锁,
    # 不可重入, 禁止在锁内调用): 角色走角色表, 实例分配 instance_id。
    stackables = []
    for item_id, num in reward_list:
        if not item_id or num <= 0:
            continue
        if item_id in unlock_candidates and item_id not in unlock_ids:
            unlock_ids.append(item_id)
        if _is_character_item(item_id):
            det = ItemDetail()
            grant_character(
                player_id,
                item_id,
                det,
                pack_notice=pack_notice,
            )
            totals.append(det)
            if rsp_items is not None:
                gain = ItemDetail()
                gain.CopyFrom(det)
                rsp_items.add().CopyFrom(gain)
            if pack_notice is not None:
                pack_notice.items.add().CopyFrom(det)
            continue
        if _tag_of(item_id) in Config.ITEM_MGR_INSTANCE_TAGS:
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
            continue
        stackables.append((item_id, num))
    level_exp = None
    ability_ids = {
        row["need_item_i_d"]: row["i_d"] for row in res["Ability"]["ability"]["datas"]
    }
    new_abilities = []
    with player_lock(player_id):
        for item_id, num in stackables:
            # 玩家经验(1): 同步入玩家等级并推送 PlayerLevelExpNotice
            if item_id == 1 and session is not None:
                level_exp = db.add_player_exp(player_id, num)
            detail = _load(player_id, item_id)
            gained_new = detail.main_item.is_new
            ability_id = ability_ids.get(item_id)
            if ability_id and detail.main_item.base_item.num == 0:
                if db.get_kv(player_id, "ability", ability_id) is None:
                    db.set_kv(player_id, "ability", ability_id, 0)
                    new_abilities.append(ability_id)
            if detail.main_item.WhichOneof("item") == "base_item":
                detail.main_item.base_item.num += num
            db.set_item_detail(player_id, detail.SerializeToString(), item_id, None)
            totals.append(detail)
            if rsp_items is not None:
                gain = ItemDetail()
                gain.CopyFrom(detail)
                if gain.main_item.WhichOneof("item") == "base_item":
                    gain.main_item.base_item.num = num
                gain.main_item.is_new = gained_new
                rsp_items.add().CopyFrom(gain)
            if pack_notice is not None:
                pack_notice.items.add().CopyFrom(detail)
    if level_exp is not None:
        notice = PlayerLevelExpNotice()
        notice.status = StatusCode.StatusCode_OK
        notice.level, notice.exp = level_exp
        session.send(MsgId.PlayerLevelExpNotice, notice, 0)
        # 成就: 玩家等级达到X级(事件层状态判定, 35/36 由 achieve_track 归族)
        achieve_track.report(session, "player_level", level=level_exp[0])
    # 物品已落库且玩家物品锁已释放后再推进任务, 避免任务即时奖励重入该锁。
    if session is not None:
        for item_id, num in reward_list:
            achieve_track.report(session, "gain_item", match=item_id, amount=num)
    if unlock_order is not None:
        unlock_ids = [
            function_id for function_id in unlock_order if function_id in unlock_ids
        ]
    new_unlocks = db.add_unlock_functions(player_id, unlock_ids)
    if session is not None and new_unlocks:
        for function_id in new_unlocks:
            unlock_notice = PlayerUnlockFunctionNotice()
            unlock_notice.status = StatusCode.StatusCode_OK
            unlock_notice.unlock_functions.append(function_id)
            session.send(MsgId.PlayerUnlockFunctionNotice, unlock_notice, 0)
    if auto_notice is not None and auto_notice.items:
        session.send(MsgId.PackNotice, auto_notice, 0)
    if session is not None:
        for ability_id in new_abilities:
            notice = PlayerAbilityUnlockNotice()
            notice.status = StatusCode.StatusCode_OK
            notice.ability_id = ability_id
            session.send(MsgId.PlayerAbilityUnlockNotice, notice, 0)
    return totals


def needs_temp_pack(detail):
    """世界掉落的装备实例和材料占临时背包；货币、衣装等直接到账。"""
    return (
        _is_instance(detail)
        or detail.main_item.item_tag == EBagItemTag.EBagItemTag_Material
    )


def pickup_rewards(session, items, rsp_items, pack_notice, to_inventory=False):
    """保留掉落实例与属性，统一拾取同步；扫荡可直接入仓库。"""
    for source in items:
        item = ItemDetail()
        item.CopyFrom(source)
        item.pack_type = ItemDetail.PackType.PackType_Inventory
        instance_id = 0
        if _is_instance(item):
            mark_new_item(session.player_id, item)
            which = item.main_item.WhichOneof("item")
            instance_id = getattr(item.main_item, which).instance_id
            db.set_item_detail(
                session.player_id, item.SerializeToString(), None, instance_id
            )
            achieve_track.report(session, "gain_item", match=item.main_item.item_id)
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
            # 材料先存实际库存，客户端本次只显示临时包中的获得量。
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
        item.pack_type = ItemDetail.PackType.PackType_TempPack
        item.main_item.temp_pack_index = len(session.temp_pack) + 1
        rsp_items.add().CopyFrom(item)
        pack_notice.items.add().CopyFrom(item)
        # 首获提示只属于本次拾取；排序、入库等临时包回放不再提示。
        item.main_item.is_new = False
        session.temp_pack.append((instance_id, item.SerializeToString()))


def consume_items(player_id, cost_list, pack_notice=None, session=None):
    """扣除 [(item_id, num), ...]: 先整体校验后统一落库(要么全扣要么不扣)。

    同种物品多条会先合并。足够则扣除并返回 True(pack_notice 填扣除后总量);
    任一不足返回 False 且不产生任何扣除。
    """
    merged = {}
    for item_id, num in cost_list:
        if not item_id or num <= 0:
            continue
        merged[item_id] = merged.get(item_id, 0) + num
    if not merged:
        return True
    with player_lock(player_id):
        details = {}
        for item_id, need in merged.items():
            raw = db.get_item_detail(player_id, item_id)
            if not raw:
                return False
            detail = ItemDetail()
            detail.ParseFromString(raw)
            if detail.main_item.base_item.num < need:
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
        for item_id, num in cost_list:
            if item_id == 101 and num > 0:
                achieve_track.report(session, "spend_coin", amount=num)
    return True
