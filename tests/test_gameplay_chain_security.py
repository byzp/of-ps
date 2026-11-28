import contextlib
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import (
    ExploreCancelReq,
    ExploreCollectRewardReq,
    ExploreQuickFinishReq,
    ExploreReq,
    ExploreRewardReq,
    EBagItemTag,
    GatherReq,
    ItemDetail,
    ItemUseReq,
    PickupReq,
    StatusCode,
    TreasureBoxData,
    TreasureBoxOpenReq,
    TreasureBoxPickupReq,
    TreasureBoxState_Open,
)
import handlers.Explore as explore
import handlers.ExploreCancel as explore_cancel
import handlers.ExploreCollectReward as explore_collect
import handlers.Gather as gather
import handlers.ItemUse as item_use
import handlers.Pickup as pickup
import handlers.TempPackItemStore as temp_store
import handlers.TreasureBoxOpen as box_open
import handlers.TreasureBoxPickup as box_pickup
import server.minigames as minigames
import server.scene_data as scene_data
import utils.db as db
import utils.res_loader as res_loader
from utils import item_mgr, pb_create
from utils import treasure_box as tb_idx


class FakeSession:
    def __init__(self, player_id=1, scene_id=1, channel_id=1):
        self.player_id = player_id
        self.player_name = "ChainTest"
        self.scene_id = scene_id
        self.channel_id = channel_id
        self.running = True
        self.dungeon = [0, 0, 0, -1]
        self.dungeon_token = ""
        self.quests = {}
        self.temp_pack = []
        self.drop_items = {}
        self.drop_lock = threading.RLock()
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))

    def response(self, message_id):
        return [message for mid, message, _ in self.sent if mid == message_id][-1]


@pytest.fixture(autouse=True)
def game_db(tmp_path, monkeypatch):
    res_loader.init()
    old_path = Config.DB_PATH
    old_memory = Config.IN_MEMORY
    Config.DB_PATH = str(tmp_path / "chain.db")
    Config.IN_MEMORY = False
    db.exit()
    db.init()
    for player_id in (1, 2):
        db.conn.execute(
            "INSERT INTO players(player_id,player_name,level,world_level,unlock_functions) "
            "VALUES (?,?,10,1,?)",
            (player_id, f"P{player_id}", pickle.dumps([])),
        )
    monkeypatch.setattr(item_mgr.achieve_track, "report", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        item_mgr.achieve_track, "batch", lambda session: contextlib.nullcontext()
    )
    monkeypatch.setattr(
        item_mgr.achieve_track, "explore_box_open", lambda *args, **kwargs: None
    )
    yield
    db.exit()
    Config.DB_PATH = old_path
    Config.IN_MEMORY = old_memory


def _gather_request(session, *, lucky=False):
    scene = next(
        row for row in res_loader.res["ScenesConfigAsset"]["Scenes"]
        if row["ID"] == session.scene_id
    )
    pointers = [
        pointer
        for group in scene["GatherPointSetInfo"]
        for point_group in group["GatherPointSets"]
        for pointer in point_group.get("LifeGatherPointers", ())
    ]
    groups = {row["i_d"]: row for row in res_loader.res["Gather"]["gather"]["datas"]}
    rewards = {
        row["i_d"]: row for row in res_loader.res["Gather"]["gather_reward"]["datas"]
    }
    for pointer in pointers:
        info = groups[pointer["GatherID"]]["gather_group_info"][0]
        choices = rewards[info["reward"]]["gather_reward_group_info"]
        if not lucky or any(choice.get("lucky") for choice in choices):
            return GatherReq(
                gather_item={
                    "index": pointer["Index"],
                    "reward": info["reward"],
                    "is_lucky": False,
                }
            )
    raise AssertionError("no suitable gather point")


def _gather(session, request):
    gather.Handler().handle(session, request.SerializeToString(), 1)
    return session.response(MsgId.GatherRsp)


def _material_item(count=2):
    item_id = next(
        row["i_d"] for row in res_loader.res["Item"]["item"]["datas"]
        if row.get("new_bag_item_tag") == EBagItemTag.EBagItemTag_Material
    )
    return item_id, pb_create.make_item(item_id, count, 1)


def _drop(session, item, index=1):
    session.drop_items[index] = [item.SerializeToString()]


def _pickup(session, drop_index=1, pick_index=-1):
    pickup.Handler().handle(
        session,
        PickupReq(drop_item_index=drop_index, pick_index=pick_index).SerializeToString(),
        1,
    )
    return session.response(MsgId.PickupRsp)


def _open(session, index=12, box_type=0, loc_type=0):
    box_open.Handler().handle(
        session,
        TreasureBoxOpenReq(
            box_type=box_type, treasure_box_index=index, loc_type=loc_type
        ).SerializeToString(),
        1,
    )
    return session.response(MsgId.TreasureBoxOpenRsp)


def _box_pickup(session, index=12, pick_index=-1, box_type=0, loc_type=0):
    box_pickup.Handler().handle(
        session,
        TreasureBoxPickupReq(
            box_type=box_type,
            box_index=index,
            pick_index=pick_index,
            loc_type=loc_type,
        ).SerializeToString(),
        1,
    )
    return session.response(MsgId.TreasureBoxPickupRsp)


def _concurrently(calls):
    barrier = threading.Barrier(len(calls))

    def invoke(call):
        barrier.wait()
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        return list(executor.map(invoke, calls))


def test_gather_rejects_forged_scene_index_and_reward_pair():
    session = FakeSession()
    request = _gather_request(session)
    request.gather_item.index = 3
    assert _gather(session, request).status == StatusCode.StatusCode_CFG_NOT_FOUND
    request = _gather_request(session)
    request.gather_item.reward = 999999
    assert _gather(session, request).status == StatusCode.StatusCode_CFG_NOT_FOUND
    assert not db.get_kv_keys(1, "gather_daily")


def test_gather_lucky_flag_is_client_untrusted_and_server_selected():
    session = FakeSession()
    request = _gather_request(session, lucky=True)
    request.gather_item.is_lucky = False
    reward_id = request.gather_item.reward
    reward = next(
        row for row in res_loader.res["Gather"]["gather_reward"]["datas"]
        if row["i_d"] == reward_id
    )
    with patch.object(gather.random, "random", return_value=0.0), patch.object(
        Config, "GATHER_LUCKY_CHANCE", 1.0
    ):
        rsp = _gather(session, request)
    assert rsp.status == StatusCode.StatusCode_OK
    lucky_pairs = {
        (choice["item_i_d"], choice["count"])
        for choice in reward["gather_reward_group_info"]
        if choice.get("lucky")
    }
    assert (rsp.items[0].main_item.item_id, rsp.items[0].main_item.base_item.num) in lucky_pairs


def test_gather_save_failure_rolls_back_item_daily_count_and_cooldown():
    session = FakeSession()
    request = _gather_request(session)
    real_set_kv = db.set_kv

    def fail_cooldown(player_id, namespace, key, value):
        if namespace == "gather_points":
            raise RuntimeError("synthetic cooldown save failure")
        return real_set_kv(player_id, namespace, key, value)

    with patch.object(db, "set_kv", side_effect=fail_cooldown):
        with pytest.raises(RuntimeError, match="synthetic"):
            _gather(session, request)
    assert not db.get_kv_keys(1, "gather_daily")
    assert not db.get_kv_keys(1, "gather_points")
    assert not db.get_item_detail(1)


def test_concurrent_pickup_grants_once_and_replay_is_rejected():
    item_id, item = _material_item()
    sessions = [FakeSession() for _ in range(8)]
    for session in sessions:
        session.drop_items = sessions[0].drop_items
        session.temp_pack = sessions[0].temp_pack
        session.drop_lock = sessions[0].drop_lock
    _drop(sessions[0], item)
    statuses = _concurrently([lambda s=s: _pickup(s).status for s in sessions])
    assert statuses.count(StatusCode.StatusCode_OK) == 1
    assert statuses.count(StatusCode.StatusCode_FAIL) == 7
    assert item_mgr.get_num(1, item_id) == 2
    assert len(sessions[0].temp_pack) == 1
    assert len(db.get_claimed(1, "drop_pickup")) == 1
    # 即使会话层再次回放同一掉落, 持久去重仍然拒绝第二次发放。
    _drop(sessions[0], item)
    assert _pickup(sessions[0]).status == StatusCode.StatusCode_REPEAT_GET_REWARD
    assert item_mgr.get_num(1, item_id) == 2


def test_pickup_rejects_invalid_index_without_consuming_drop():
    _, item = _material_item()
    session = FakeSession()
    _drop(session, item)
    assert _pickup(session, pick_index=0).status == StatusCode.StatusCode_BAD_REQ
    assert len(session.drop_items[1]) == 1
    assert not db.get_claimed(1, "drop_pickup")


def test_pickup_item_save_failure_preserves_drop_temp_pack_and_claim():
    item_id, item = _material_item()
    session = FakeSession()
    _drop(session, item)
    with patch.object(db, "set_item_detail", side_effect=RuntimeError("synthetic item save")):
        with pytest.raises(RuntimeError, match="synthetic"):
            _pickup(session)
    assert len(session.drop_items[1]) == 1
    assert session.temp_pack == []
    assert item_mgr.get_num(1, item_id) == 0
    assert not db.get_claimed(1, "drop_pickup")
    assert _pickup(session).status == StatusCode.StatusCode_OK
    assert item_mgr.get_num(1, item_id) == 2


def test_temp_pack_store_does_not_duplicate_prewritten_material():
    item_id, item = _material_item(3)
    session = FakeSession()
    _drop(session, item)
    assert _pickup(session).status == StatusCode.StatusCode_OK
    temp_store.Handler().handle(session, b"", 1)
    assert item_mgr.get_num(1, item_id) == 3
    assert session.temp_pack == []


def test_treasure_open_save_failure_leaves_no_record_and_retry_succeeds():
    session = FakeSession()
    _, reward = _material_item(1)
    with patch.object(db, "set_treasure_box", side_effect=RuntimeError("synthetic box save")), patch.object(
        box_open, "make_treasure_box_item", return_value=[reward]
    ):
        with pytest.raises(RuntimeError, match="synthetic"):
            _open(session)
    assert db.get_treasure_box(1, "scene:1:12") is None
    with patch.object(box_open, "make_treasure_box_item", return_value=[reward]):
        assert _open(session).status == StatusCode.StatusCode_OK


def test_treasure_open_missing_generated_reward_is_rejected():
    session = FakeSession()
    with patch.object(box_open, "make_treasure_box_item", return_value=[]):
        assert _open(session).status == StatusCode.StatusCode_CFG_NOT_FOUND
    assert db.get_treasure_box(1, "scene:1:12") is None


def test_treasure_open_replay_returns_same_rewards_without_new_generation():
    session = FakeSession()
    item_id, item = _material_item(4)
    with patch.object(box_open, "make_treasure_box_item", return_value=[item]) as generate:
        first = _open(session)
        second = _open(FakeSession())
    assert first.status == second.status == StatusCode.StatusCode_OK
    assert first.items == second.items
    assert generate.call_count == 1
    assert item_mgr.get_num(1, item_id) == 0


def test_concurrent_treasure_pickup_grants_once():
    item_id, item = _material_item(2)
    opener = FakeSession()
    with patch.object(box_open, "make_treasure_box_item", return_value=[item]):
        assert _open(opener).status == StatusCode.StatusCode_OK
    sessions = [FakeSession() for _ in range(8)]
    statuses = _concurrently([lambda s=s: _box_pickup(s).status for s in sessions])
    assert statuses.count(StatusCode.StatusCode_OK) == 1
    assert statuses.count(StatusCode.StatusCode_REPEAT_GET_REWARD) == 7
    assert item_mgr.get_num(1, item_id) == 2
    assert sum(len(session.temp_pack) for session in sessions) == 1
    saved = TreasureBoxData.FromString(db.get_treasure_box(1, "scene:1:12"))
    assert not saved.rewards


def test_treasure_pickup_cost_and_reward_roll_back_together_on_save_failure():
    cost_item, cost_count = 11, 2
    item_id, reward = _material_item(2)
    item_mgr.grant_items(1, [(cost_item, 5)])
    session = FakeSession()
    resolved = tb_idx.resolve(session, 0, 12, 0)
    assert resolved is not None
    store_key, cfg_id = resolved
    box = TreasureBoxData(index=12, box_id=cfg_id, state=TreasureBoxState_Open)
    box.rewards.add().CopyFrom(reward)
    db.set_treasure_box(1, store_key, box.SerializeToString())
    db.set_kv(1, "dungeon_box_multiple", store_key, 1)
    cfg = {
        "i_d": 1001,
        "new_consumption_mode": Config.DUNGEON_BOX_CONSUMPTION_MODE,
        "item_i_d": cost_item,
        "item_num": cost_count,
    }
    with patch.object(box_pickup, "material_dungeon", return_value=cfg), patch.object(
        db, "set_treasure_box", side_effect=RuntimeError("synthetic box pickup save")
    ):
        with pytest.raises(RuntimeError, match="synthetic"):
            _box_pickup(session)
    assert item_mgr.get_num(1, cost_item) == 5
    assert item_mgr.get_num(1, item_id) == 0
    assert db.get_kv(1, "dungeon_box_paid", store_key, 0) == 0
    assert session.temp_pack == []
    assert TreasureBoxData.FromString(db.get_treasure_box(1, store_key)).rewards
    with patch.object(box_pickup, "material_dungeon", return_value=cfg):
        assert _box_pickup(session).status == StatusCode.StatusCode_OK
    assert item_mgr.get_num(1, cost_item) == 3
    assert item_mgr.get_num(1, item_id) == 2


def test_activity_explore_cancel_returns_reserved_attempt():
    cfg = explore.activity_config(901)
    assert cfg is not None
    # Use the real configured cap, but make the assertion independent of its value.
    max_times = int(cfg.get("max_times", 0) or 0)
    if max_times:
        state = explore.load_activity_state(1, str(cfg["i_d"]))
        state.update(times=max_times - 1, start_time=0, is_quick_finish=False)
        explore.save_activity_state(1, str(cfg["i_d"]), state)
    session = FakeSession()
    explore.Handler().handle(session, ExploreReq(explore_id=901, is_activity=True).SerializeToString(), 1)
    assert session.response(MsgId.ExploreRsp).status == StatusCode.StatusCode_OK
    before = explore.load_activity_state(1, str(cfg["i_d"]))["times"]
    explore_cancel.Handler().handle(
        session, ExploreCancelReq(explore_id=901, is_activity=True).SerializeToString(), 1
    )
    assert session.response(MsgId.ExploreCancelRsp).status == StatusCode.StatusCode_OK
    assert explore.load_activity_state(1, str(cfg["i_d"]))["times"] == before - 1
    retry = FakeSession()
    explore.Handler().handle(retry, ExploreReq(explore_id=901, is_activity=True).SerializeToString(), 1)
    assert retry.response(MsgId.ExploreRsp).status == StatusCode.StatusCode_OK


def test_explore_collect_cannot_be_claimed_before_first_completion():
    session = FakeSession()
    explore_collect.Handler().handle(
        session, ExploreCollectRewardReq(explore_id=10101).SerializeToString(), 1
    )
    assert session.response(MsgId.ExploreCollectRewardRsp).status == StatusCode.StatusCode_EXPLORE_NOT_FINISH
    assert not db.get_claimed(1, "got_ids")


def test_area_entry_cost_is_charged_and_save_failure_refunds_it():
    cfg = dict(explore.garden_state.explore_area_cfg(10101))
    cfg.update(need_item=102, need_item_count=1)
    item_mgr.grant_items(1, [(102, 1)])
    session = FakeSession()
    real_set_kv = db.set_kv

    def fail_explore(player_id, namespace, key, value):
        if namespace == "explore":
            raise RuntimeError("synthetic explore save")
        return real_set_kv(player_id, namespace, key, value)

    with patch.object(explore.garden_state, "explore_area_cfg", return_value=cfg), patch.object(
        db, "set_kv", side_effect=fail_explore
    ):
        with pytest.raises(RuntimeError, match="synthetic"):
            explore.Handler().handle(session, ExploreReq(explore_id=10101).SerializeToString(), 1)
    assert item_mgr.get_num(1, 102) == 1
    assert explore.load_area_state(1, 10101)["start_time"] == 0
    with patch.object(explore.garden_state, "explore_area_cfg", return_value=cfg):
        explore.Handler().handle(session, ExploreReq(explore_id=10101).SerializeToString(), 1)
    assert session.response(MsgId.ExploreRsp).status == StatusCode.StatusCode_OK
    assert item_mgr.get_num(1, 102) == 0


def test_item_use_rejects_unsupported_client_reward_choice():
    session = FakeSession()
    item_use.Handler().handle(
        session, ItemUseReq(item_id=101, num=1, choose_item_id=102).SerializeToString(), 1
    )
    assert session.response(MsgId.ItemUseRsp).status == StatusCode.StatusCode_BAD_REQ
    assert item_mgr.get_num(1, 101) == 0


def test_minigame_settlement_failure_rolls_back_every_member():
    team = {
        "team_id": 77,
        "mode_id": 1,
        "sub_mode_id": 2,
        "gameplay_id": 3,
        "game_mode": 4,
        "room": {"game_start_time": 1234},
        "members": {"1": {"character_id": 1}, "2": {"character_id": 2}},
    }
    key = (1, 2, 3, 2)
    real_grant = item_mgr.grant_items

    def fail_second(player_id, rewards, *args, **kwargs):
        if player_id == 2:
            raise RuntimeError("synthetic member grant")
        return real_grant(player_id, rewards, *args, **kwargs)

    with patch.object(Config, "MP_ROOM_REWARDS", {key: {"items": ((101, 3),)}}, create=True):
        minigames.mark_started(team, 1000)
        with patch.object(item_mgr, "grant_items", side_effect=fail_second):
            with pytest.raises(RuntimeError, match="synthetic"):
                minigames.settle(team, 2, 2000)
        assert item_mgr.get_num(1, 101) == item_mgr.get_num(2, 101) == 0
        assert minigames.load_run(team["room"]["run_id"])["status"] == "active"
        run, changed = minigames.settle(team, 2, 2000)
        assert changed and run["status"] == "settled"
        assert item_mgr.get_num(1, 101) == item_mgr.get_num(2, 101) == 3
        _, changed_again = minigames.settle(team, 2, 2000)
        assert not changed_again
        assert item_mgr.get_num(1, 101) == item_mgr.get_num(2, 101) == 3


def test_forged_saved_location_is_rejected_without_mutating_session():
    session = FakeSession(scene_id=1, channel_id=1)
    db.set_kv(
        1,
        "player_location",
        "last",
        pickle.dumps({"scene_id": 987654, "channel_id": 1, "position": b"", "rotation": b""}),
    )
    assert not scene_data.restore_session_location(session)
    assert (session.scene_id, session.channel_id) == (1, 1)
    db.set_kv(
        1,
        "player_location",
        "last",
        pickle.dumps({"scene_id": 1, "channel_id": 0, "position": b"", "rotation": b""}),
    )
    assert scene_data.load_session_location(1) is None
