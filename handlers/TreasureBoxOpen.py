import time

from config import Config
from google.protobuf.message import DecodeError
from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    TreasureBoxOpenReq,
    TreasureBoxOpenRsp,
    TreasureBoxData,
    TreasureBoxState_Open,
    ItemDetail,
    StatusCode,
    TreasureBoxLocType_DUNGEON,
    DungeonOpenFinalBoxNotice,
    TREASURE_BOX_TYPE_DYNAMIC,
    TREASURE_BOX_TYPE_STATIC,
    TreasureBoxLocType_SCENE,
)

import utils.db as db
from utils import achieve_track, dungeon_state, item_mgr
from utils import treasure_box as tb_idx
from utils.dungeon_reward import (
    material_dungeon,
    make_dungeon_rewards,
    reward_multiplier,
)
from utils.pb_create import (
    _make_box_extra,
    make_treasure_box_item,
    make_collection_box_reward,
)
from utils.res_loader import res


class _BoxNotFound(Exception):
    pass


def _config(table, cfg_id):
    section = res.get("TreasureBox", {}).get(table, {})
    rows = section.get("datas", ()) if isinstance(section, dict) else ()
    return next(
        (
            row
            for row in rows
            if isinstance(row, dict) and row.get("i_d") == cfg_id
        ),
        None,
    )


def _validate_rewards(items):
    if not items:
        raise item_mgr.EconomyConfigError("treasure box has no rewards")
    for item in items:
        item_mgr.validate_pickup_item(item)


@packet_handler(MsgId.TreasureBoxOpenReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        # 统一锁顺序: 玩家经济锁 -> 副本锁 -> 宝箱锁 -> DB 事务。
        with (
            item_mgr.player_lock(session.player_id),
            dungeon_state.player_lock(session.player_id),
            tb_idx.player_box_lock(session.player_id),
        ):
            self._handle(session, data, packet_id)

    def _handle(self, session, data, packet_id):
        req = TreasureBoxOpenReq()
        req.ParseFromString(data)
        rsp = TreasureBoxOpenRsp(status=StatusCode.StatusCode_OK)
        if (
            req.box_type not in (TREASURE_BOX_TYPE_STATIC, TREASURE_BOX_TYPE_DYNAMIC)
            or req.loc_type not in (TreasureBoxLocType_SCENE, TreasureBoxLocType_DUNGEON)
        ):
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
            return
        try:
            opened_now, cfg_id, one_time, material_cfg, treasure_cfg = self._open(
                session, req, rsp
            )
        except _BoxNotFound:
            rsp.status = StatusCode.StatusCode_TREASURE_BOX_NOT_EXIST
            session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
            return
        except (
            AttributeError,
            DecodeError,
            item_mgr.EconomyConfigError,
            KeyError,
            IndexError,
            LookupError,
            TypeError,
            ValueError,
        ):
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.items[:]
            session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
            return

        session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
        if opened_now and material_cfg:
            session.send(
                MsgId.DungeonOpenFinalBoxNotice,
                DungeonOpenFinalBoxNotice(
                    status=StatusCode.StatusCode_OK, dungeon_id=session.dungeon[0]
                ),
                0,
            )
        if not opened_now:
            return
        with achieve_track.batch(session):
            if one_time and req.loc_type != TreasureBoxLocType_DUNGEON:
                achieve_track.explore_box_open(session, box_id=cfg_id)
            achieve_track.report(session, "treasure_box")
            if req.loc_type == TreasureBoxLocType_DUNGEON:
                achieve_track.report(
                    session,
                    "dungeon_box",
                    dungeon_id=session.dungeon[0],
                    box_kind=(
                        "normal"
                        if treasure_cfg
                        and treasure_cfg.get("new_treasure_box_reward_type") == 1
                        else None
                    ),
                )

    @staticmethod
    def _open(session, req, rsp):
        resolved = tb_idx.resolve(
            session, req.box_type, req.treasure_box_index, req.loc_type
        )
        if resolved is None:
            raise _BoxNotFound("treasure box does not exist")
        store_key, cfg_id = resolved
        box_cfg = _config("collection_treasure_box", cfg_id)
        treasure_cfg = _config("treasure_box", cfg_id)
        if box_cfg is None and treasure_cfg is None:
            raise item_mgr.EconomyConfigError("missing treasure box config")

        # 一次性不可刷新收集宝箱: refresh_time==[0]。
        one_time = bool(box_cfg) and tuple(box_cfg.get("refresh_time") or ()) == (0,)
        is_dynamic = req.box_type == TREASURE_BOX_TYPE_DYNAMIC
        is_dungeon = req.loc_type == TreasureBoxLocType_DUNGEON
        material_cfg = material_dungeon(session, req.loc_type) if not is_dynamic else None
        refresh_interval = tb_idx.refresh_interval(cfg_id, is_dungeon=is_dungeon)
        refreshable = not is_dynamic and refresh_interval > 0
        tutorial = (
            not is_dungeon
            and getattr(session, "scene_id", 0) == Config.TUTORIAL_SCENE_ID
        )
        time_t = int(time.time())
        opened_now = False

        with item_mgr.deferred_notifications(), db.transaction():
            tb = TreasureBoxData()
            tb_b, used_legacy = tb_idx.load_record(
                session.player_id, store_key, req.treasure_box_index
            )
            refresh = False
            if tb_b:
                tb.ParseFromString(tb_b)
                if tb.box_id != cfg_id:
                    raise item_mgr.EconomyConfigError("treasure box config mismatch")
                stored_refresh_time = tb.next_refresh_time
                tb.next_refresh_time = tb_idx.normalize_refresh_time(tb.next_refresh_time)
                item_mgr.validate_counter(tb.next_refresh_time, label="box refresh time")
                changed = tb.next_refresh_time != stored_refresh_time
                if tb.state != TreasureBoxState_Open:
                    tb.state = TreasureBoxState_Open
                    changed = True
                if one_time and not tutorial and tb.next_refresh_time == 0:
                    tb.next_refresh_time = Config.PERMANENT_BOX_REFRESH_TIME
                    changed = True
                if refreshable and tb.next_refresh_time <= 0:
                    if not tb.rewards:
                        refresh = True
                    else:
                        # 保留旧记录待领取奖励, 从本次开启时重新计时。
                        tb.next_refresh_time = item_mgr.checked_add(
                            time_t,
                            refresh_interval,
                            limit=Config.ECONOMY_UINT32_MAX,
                        )
                        changed = True
                elif refreshable and tb.next_refresh_time <= time_t:
                    refresh = True
                if not refresh:
                    _validate_rewards(list(tb.rewards))
                    for item in tb.rewards:
                        rsp.items.add().CopyFrom(item)
                    if changed or used_legacy:
                        db.set_treasure_box(
                            session.player_id, store_key, tb.SerializeToString()
                        )
            if not tb_b or refresh:
                opened_now = True
                tb = TreasureBoxData()
                tb.index = req.treasure_box_index
                tb.box_id = cfg_id
                tb.state = TreasureBoxState_Open
                if refreshable:
                    tb.next_refresh_time = item_mgr.checked_add(
                        time_t,
                        refresh_interval,
                        limit=Config.ECONOMY_UINT32_MAX,
                    )
                elif one_time and not tutorial:
                    tb.next_refresh_time = Config.PERMANENT_BOX_REFRESH_TIME
                if material_cfg:
                    multiple = item_mgr.validate_count(
                        reward_multiplier(session.player_id, material_cfg["i_d"]),
                        label="dungeon reward multiplier",
                    )
                    if multiple not in Config.DUNGEON_REWARD_MULTIPLIERS:
                        raise item_mgr.EconomyConfigError("invalid dungeon multiplier")
                    box_items = make_dungeon_rewards(
                        session.player_id, material_cfg, multiple
                    )
                    db.set_kv(
                        session.player_id,
                        "dungeon_box_multiple",
                        store_key,
                        multiple,
                    )
                elif tutorial:
                    reward = Config.TUTORIAL_BOX_REWARDS.get(cfg_id)
                    if reward is None:
                        raise item_mgr.EconomyConfigError("missing tutorial box reward")
                    box_items = _make_box_extra(*reward, session.player_id)
                elif one_time and not is_dungeon:
                    box_items = make_collection_box_reward(
                        session.player_id,
                        cfg_id,
                        reward_type=(
                            treasure_cfg.get("new_treasure_box_reward_type")
                            if treasure_cfg
                            else None
                        ),
                    )
                else:
                    world_row = db.get_players_info(session.player_id, "world_level")
                    world_level = world_row[0] if world_row else 0
                    box_items = make_treasure_box_item(
                        session.player_id,
                        world_level,
                        scene_id=getattr(session, "scene_id", None),
                        box_id=cfg_id,
                    )
                    if (
                        is_dungeon
                        and not is_dynamic
                        and treasure_cfg
                        and treasure_cfg.get("new_treasure_box_reward_type") == 2
                    ):
                        for item_id, count in Config.DUNGEON_FINAL_BOX_REWARDS:
                            box_items.extend(
                                _make_box_extra(item_id, count, session.player_id)
                            )
                _validate_rewards(box_items)
                for item in box_items:
                    if item.main_item.WhichOneof("item") != "outfit":
                        item.pack_type = ItemDetail.PackType.PackType_TempStorageArea
                    tb.rewards.add().CopyFrom(item)
                    rsp.items.add().CopyFrom(item)
                if (
                    is_dungeon
                    and treasure_cfg
                    and treasure_cfg.get("new_treasure_box_reward_type") == 4
                ):
                    dg = dungeon_state.load(session.player_id, session.dungeon[0])
                    dg.is_open_secret_box = True
                    dungeon_state.save(session, dg)
                db.set_treasure_box(
                    session.player_id, store_key, tb.SerializeToString()
                )
            rsp.next_refresh_time = tb.next_refresh_time * 1000
        return opened_now, cfg_id, one_time, material_cfg, treasure_cfg
