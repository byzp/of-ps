from config import Config
import time

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
)

import utils.db as db
from utils import achieve_track, dungeon_state
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


@packet_handler(MsgId.TreasureBoxOpenReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with (
            dungeon_state.player_lock(session.player_id),
            tb_idx.player_box_lock(session.player_id),
        ):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = TreasureBoxOpenReq()
        req.ParseFromString(data)

        rsp = TreasureBoxOpenRsp()
        rsp.status = StatusCode.StatusCode_OK

        resolved = tb_idx.resolve(
            session, req.box_type, req.treasure_box_index, req.loc_type
        )
        if resolved is None:
            rsp.status = StatusCode.StatusCode_TREASURE_BOX_NOT_EXIST
            session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
            return
        store_key, cfg_id = resolved

        # 一次性不可刷新收集宝箱: collection_treasure_box.refresh_time==[0]
        # (特殊奖励: 时装/染剂/伞等, 计入场景探索度, 开启后永久关闭)
        box_cfg = None
        for e in res["TreasureBox"]["collection_treasure_box"]["datas"]:
            if isinstance(e, dict) and e.get("i_d") == cfg_id:
                box_cfg = e
                break
        treasure_cfg = None
        for e in res["TreasureBox"]["treasure_box"]["datas"]:
            if isinstance(e, dict) and e.get("i_d") == cfg_id:
                treasure_cfg = e
                break
        one_time = bool(box_cfg) and tuple(box_cfg.get("refresh_time") or ()) == (0,)
        is_dynamic = req.box_type == 1
        is_dungeon = req.loc_type == TreasureBoxLocType_DUNGEON
        material_cfg = (
            material_dungeon(session, req.loc_type) if not is_dynamic else None
        )
        refresh_interval = tb_idx.refresh_interval(cfg_id, is_dungeon=is_dungeon)
        refreshable = not is_dynamic and refresh_interval > 0

        tb = TreasureBoxData()
        tb_b, used_legacy = tb_idx.load_record(
            session.player_id, store_key, req.treasure_box_index
        )
        refresh = False
        opened_now = not tb_b
        tutorial = (
            not is_dungeon
            and getattr(session, "scene_id", 0) == Config.TUTORIAL_SCENE_ID
        )
        time_t = int(time.time())
        if tb_b:
            tb.ParseFromString(tb_b)
            stored_refresh_time = tb.next_refresh_time
            tb.next_refresh_time = tb_idx.normalize_refresh_time(tb.next_refresh_time)
            changed = tb.next_refresh_time != stored_refresh_time
            if tb.state != TreasureBoxState_Open:
                tb.state = TreasureBoxState_Open
                changed = True
            if refreshable and tb.next_refresh_time <= 0:
                if not tb.rewards:
                    refresh = True
                    opened_now = True
                else:
                    # 保留旧记录中的待领取奖励, 并从本次开启时开始计时。
                    tb.next_refresh_time = time_t + refresh_interval
                    changed = True
            elif refreshable and tb.next_refresh_time <= time_t:
                refresh = True
                opened_now = True
            if not refresh:
                for item in tb.rewards:
                    rsp.items.add().CopyFrom(item)
                if changed or used_legacy:
                    db.set_treasure_box(
                        session.player_id, store_key, tb.SerializeToString()
                    )
        if not tb_b or refresh:
            tb = TreasureBoxData()
            tb.index = req.treasure_box_index
            tb.box_id = cfg_id
            tb.state = TreasureBoxState_Open
            if refreshable:
                tb.next_refresh_time = time_t + refresh_interval
            if material_cfg:
                multiple = reward_multiplier(session.player_id, material_cfg["i_d"])
                box_items = make_dungeon_rewards(
                    session.player_id, material_cfg, multiple
                )
                db.set_kv(
                    session.player_id, "dungeon_box_multiple", store_key, multiple
                )
            elif tutorial:
                box_items = _make_box_extra(
                    *Config.TUTORIAL_BOX_REWARDS.get(
                        cfg_id,
                        (Config.TUTORIAL_BOX_COIN_ID, Config.TUTORIAL_BOX_COIN_NUM),
                    ),
                    session.player_id,
                )
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
                box_items = make_treasure_box_item(
                    session.player_id,
                    db.get_players_info(session.player_id, "world_level")[0],
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
            for item in box_items:
                if item.main_item.WhichOneof("item") != "outfit":
                    item.pack_type = ItemDetail.PackType.PackType_TempStorageArea
                tb.rewards.add().CopyFrom(item)
                rsp.items.add().CopyFrom(item)
            db.set_treasure_box(session.player_id, store_key, tb.SerializeToString())

        rsp.next_refresh_time = tb.next_refresh_time * 1000

        if opened_now and material_cfg:
            session.send(
                MsgId.DungeonOpenFinalBoxNotice,
                DungeonOpenFinalBoxNotice(
                    status=StatusCode.StatusCode_OK, dungeon_id=session.dungeon[0]
                ),
                0,
            )
        session.send(MsgId.TreasureBoxOpenRsp, rsp, packet_id)
        if opened_now:
            with achieve_track.batch(session):
                if one_time and not is_dungeon:
                    # 成就/探索度: 一次性收集点位计入场景完成度
                    achieve_track.explore_box_open(session, box_id=cfg_id)
                # 成就: 开宝箱(任意场景箱子 + 按世界/场景"翻翻找找", 事件层归族)
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
                    dg = dungeon_state.load(session.player_id, session.dungeon[0])
                    if (
                        treasure_cfg
                        and treasure_cfg.get("new_treasure_box_reward_type") == 4
                    ):
                        dg.is_open_secret_box = True
                    dungeon_state.save(session, dg)
