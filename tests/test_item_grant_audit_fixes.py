import concurrent.futures
import contextlib
import pickle
import threading

import pytest

from config import Config
from network.msg_id import MsgId
from proto.net_pb2 import (
    AbilityBadgeAchieveRewardReq,
    AreaUnlockReq,
    CollectionRewardReq,
    CollectingReq,
    DailyTaskExchangeReq,
    DungeonSweepReq,
    GetOneAchieveAwardReq,
    ItemSweepReq,
    MonsterDeadReq,
    PBCollectionRewardData,
    RewardStatus,
    StatusCode,
    TreasureDigReq,
)
import handlers.AbilityBadgeAchieveReward as badge
import handlers.AreaUnlock as area
import handlers.CollectionReward as collection_reward
import handlers.Collecting as collecting
import handlers.DailyTaskExchange as daily
import handlers.DungeonSweep as dungeon_sweep
import handlers.GetOneAchieveAward as achieve
import handlers.ItemSweep as item_sweep
import handlers.MonsterDead as monster_dead
import handlers.TreasureDig as treasure_dig
import utils.db as db
import utils.res_loader as res_loader
from utils import item_mgr
from utils.pb_create import make_item


class FakeSession:
    def __init__(self, player_id=1, scene_id=1):
        self.player_id = player_id
        self.player_name = "AuditFix"
        self.scene_id = scene_id
        self.channel_id = 1
        self.running = True
        self.dungeon = [0, 0, 0, -1]
        self.dungeon_token = ""
        self.world_run_token = ""
        self.world_monster_tokens = {}
        self.temp_pack = []
        self.drop_items = {}
        self.drop_lock = threading.RLock()
        self.sent = []

    def send(self, message_id, message, packet_id=0):
        self.sent.append((message_id, message, packet_id))

    def response(self, message_id):
        return [message for mid, message, _ in self.sent if mid == message_id][-1]


@pytest.fixture(scope="module", autouse=True)
def resources():
    res_loader.init()


@pytest.fixture(autouse=True)
def game_db(tmp_path, monkeypatch):
    old_path, old_memory = Config.DB_PATH, Config.IN_MEMORY
    Config.DB_PATH = str(tmp_path / "audit-fix.db")
    Config.IN_MEMORY = False
    db.exit()
    db.init()
    db.conn.execute(
        "INSERT INTO players(player_id,player_name,level,world_level,unlock_functions) "
        "VALUES (1,'AuditFix',10,1,?)",
        (pickle.dumps([]),),
    )
    monkeypatch.setattr(item_mgr.achieve_track, "report", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        item_mgr.achieve_track, "batch", lambda session: contextlib.nullcontext()
    )
    for name in (
        "sync_scoped_progress", "collection", "explore_collect", "progress",
    ):
        monkeypatch.setattr(item_mgr.achieve_track, name, lambda *args, **kwargs: 0)
    yield
    db.exit()
    Config.DB_PATH, Config.IN_MEMORY = old_path, old_memory


def grant(item_id, count):
    item_mgr.grant_items(1, [(item_id, count)])


def num(item_id):
    return item_mgr.get_num(1, item_id)


def has_treasure_map():
    from proto.net_pb2 import ItemDetail
    return any(
        ItemDetail.FromString(blob).main_item.item_id == 5070001
        for blob in db.get_item_detail(1)
    )


def concurrently(calls):
    barrier = threading.Barrier(len(calls))

    def invoke(call):
        barrier.wait()
        return call()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(calls)) as executor:
        return list(executor.map(invoke, calls))


def install_resources(patch, resources):
    if hasattr(patch, "setitem"):
        for name, value in resources.items():
            patch.setitem(res_loader.res, name, value)
    else:
        patch.dict(res_loader.res, resources)


def send(handler, session, request, response_id):
    handler.Handler().handle(session, request.SerializeToString(), 1)
    return session.response(response_id)


def daily_resources(cost=2):
    return {"DailyTask": {"daily_task_reward": {"datas": [
        {"i_d": 1, "cost_item_i_d": 124, "cost_item_num": cost},
        {"i_d": 2, "cost_item_i_d": 124, "cost_item_num": cost},
    ]}}}


def quick_resources(*, vitality=2, yield_count=1):
    return {"QuickObtaining": {"quick_obtaining": {"datas": [{
        "i_d": 102,
        "quick_obtaining_item": [{"player_level": 1, "num": yield_count, "need_vitality": vitality}],
    }]}}}


def collection_resources():
    return {"CollectionItem": {
        "collection_item": {"datas": [{"i_d": 9001, "new_collection_type": 1, "relate_i_d": 9001}]},
        "collection_item_file": {"datas": [{"i_d": 9001, "reward_i_d": 7001}]},
    }}


def badge_resources(item_id=102):
    return {"MoonStone": {
        "stone_reward_quest_data": {"datas": [{
            "i_d": 11,
            "stone_reward_quest_data_group_info": [{"achieve_condition_i_d": 501}],
        }]},
        "stone_area_data": {"datas": [{"i_d": 1, "reward_quest_i_d": 11, "item_i_d": item_id}]},
    }}


def test_of001_world_monster_without_authority_is_rejected_without_rewards(monkeypatch):
    session = FakeSession()
    req = MonsterDeadReq(monster_id=1405, monster_index=0)
    with monkeypatch.context() as patch:
        patch.setattr(monster_dead, "_monster_reward_id", lambda _: 107)
        patch.setattr(monster_dead, "resolve_drop", lambda *args: [(102, 5)])
        rsp = send(monster_dead, session, req, MsgId.MonsterDeadRsp)
    assert rsp.status == StatusCode.StatusCode_FAIL
    assert not rsp.drop_item.items and not session.drop_items
    assert num(102) == 0 and not db.get_claimed(1, "monster_kill")


def test_of001_scalar_run_token_cannot_forge_other_monster_instances(monkeypatch):
    session, req = _authorized_world(monkeypatch)
    session.world_monster_tokens = {}
    session.world_run_token = "not-bound-to-an-instance"
    assert send(monster_dead, session, req, MsgId.MonsterDeadRsp).status == StatusCode.StatusCode_FAIL
    other_id = next(
        row["i_d"] for row in res_loader.res["Monster"]["monster_character_data"]["datas"]
        if row["i_d"] != req.monster_id
    )
    forged = MonsterDeadReq(monster_id=other_id, monster_index=0)
    assert send(monster_dead, session, forged, MsgId.MonsterDeadRsp).status == StatusCode.StatusCode_FAIL
    assert num(104) == 0 and not db.get_claimed(1, "monster_kill")


def _authorized_world(monkeypatch, *, fail_grant=False):
    session = FakeSession()
    monster_id = res_loader.res["Monster"]["monster_character_data"]["datas"][0]["i_d"]
    session.world_monster_tokens[(1, 0, monster_id)] = "server-instance-1"
    monkeypatch.setattr(monster_dead, "_monster_reward_id", lambda _: 0)
    monkeypatch.setattr(monster_dead, "_scene_types", lambda: {1: "world"})
    monkeypatch.setattr(monster_dead.monster_loot, "roll", lambda *args: [make_item(102, 2, 1)])
    monkeypatch.setattr(monster_dead.db, "has_unlock_function", lambda *args: True)
    monkeypatch.setattr(monster_dead, "resolve_reward", lambda *args: [(104, 5)])
    monkeypatch.setattr(Config, "MOON_KILL_REWARD_CHANCE", 1.0)
    if fail_grant:
        monkeypatch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
    return session, MonsterDeadReq(monster_id=monster_id, monster_index=0)


def test_of001_authorized_world_kill_claims_drop_and_direct_reward_once(monkeypatch):
    session, req = _authorized_world(monkeypatch)
    first = send(monster_dead, session, req, MsgId.MonsterDeadRsp)
    replay = send(monster_dead, session, req, MsgId.MonsterDeadRsp)
    assert first.status == StatusCode.StatusCode_OK
    assert replay.status == StatusCode.StatusCode_REPEAT_GET_REWARD
    assert len(first.drop_item.items) == 1 and not replay.drop_item.items
    assert len(session.drop_items) == 1
    assert (num(102), num(104)) == (0, 5)
    assert db.get_claimed(1, "monster_kill") == ["1:0:server-instance-1:0:" + str(req.monster_id)]


def test_of001_kill_failure_rolls_back_claim_drop_sequence_and_reward(monkeypatch):
    session, req = _authorized_world(monkeypatch, fail_grant=True)
    with pytest.raises(RuntimeError, match="grant failed"):
        send(monster_dead, session, req, MsgId.MonsterDeadRsp)
    assert not db.get_claimed(1, "monster_kill")
    assert not session.drop_items
    assert db.get_kv(1, "drop", "seq", 0) == 0
    assert num(104) == 0


def test_of001_concurrent_world_kill_replay_generates_one_drop_and_reward(monkeypatch):
    session, req = _authorized_world(monkeypatch)
    sessions = [FakeSession() for _ in range(8)]
    for other in sessions:
        other.world_monster_tokens = dict(session.world_monster_tokens)
    responses = concurrently([
        (lambda s=s: send(monster_dead, s, req, MsgId.MonsterDeadRsp)) for s in sessions
    ])
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_OK) == 1
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_REPEAT_GET_REWARD) == 7
    assert sum(len(rsp.drop_item.items) for rsp in responses) == 1
    assert num(104) == 5


def test_of002_concurrent_daily_exchange_claims_distinct_slots_once(monkeypatch):
    grant(124, 4)
    sessions = [FakeSession() for _ in range(8)]
    with monkeypatch.context() as patch:
        install_resources(patch, daily_resources())
        responses = concurrently([
            (lambda s=s: send(daily, s, DailyTaskExchangeReq(), MsgId.DailyTaskExchangeRsp))
            for s in sessions
        ])
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_OK) == 2
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_DAILY_WISH_TIMES_NOT_ENOUGH) == 6
    assert (num(124), num(Config.WISH_STONE_ITEM_ID)) == (0, 2)
    assert sorted(db.get_claimed(1, "daily_task_exchange")) == sorted(
        f"{daily.refresh.day_index()}:{idx}" for idx in (0, 1)
    )


def test_of002_daily_grant_failure_rolls_back_cost_count_and_claims(monkeypatch):
    grant(124, 2)
    session = FakeSession()
    with monkeypatch.context() as patch:
        install_resources(patch, daily_resources())
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(daily, session, DailyTaskExchangeReq(), MsgId.DailyTaskExchangeRsp)
    assert num(124) == 2 and num(Config.WISH_STONE_ITEM_ID) == 0
    assert not db.get_claimed(1, "daily_task_exchange")
    assert db.get_kv(1, "daily", f"exchange:{daily.refresh.day_index()}", 0) == 0


def test_of003_concurrent_collecting_grants_reward_once(monkeypatch):
    session = FakeSession()
    sessions = [FakeSession() for _ in range(8)]
    with monkeypatch.context() as patch:
        install_resources(patch, {
            "CollectionItem": {"collection_item": {"datas": [{"i_d": 102, "new_collection_type": 1}]}},
        })
        patch.setattr(collecting.collection_state, "scene_items", lambda *args: {})
        patch.setattr(collecting.collection_state, "fill_progress", lambda *args: None)
        responses = concurrently([
            (lambda s=s: send(collecting, s, CollectingReq(item_id=102), MsgId.CollectingRsp))
            for s in sessions
        ])
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_OK) == 1
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_ALREADY_COLLECTED) == 7
    # Item 102 的 text_i_d 是自身; 只发一次。
    assert num(102) == 1
    assert db.get_collection(1, 102)
    assert db.get_claimed(1, "collection_collect") == ["102"]


def test_of003_collecting_grant_failure_rolls_back_collection_and_claim(monkeypatch):
    session = FakeSession()
    with monkeypatch.context() as patch:
        install_resources(patch, {
            "CollectionItem": {"collection_item": {"datas": [{"i_d": 102, "new_collection_type": 1}]}},
        })
        patch.setattr(collecting.collection_state, "scene_items", lambda *args: {})
        patch.setattr(collecting.collection_state, "fill_progress", lambda *args: None)
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(collecting, session, CollectingReq(item_id=102), MsgId.CollectingRsp)
    assert not db.get_collection(1, 102)
    assert not db.get_claimed(1, "collection_collect")
    assert num(102) == 0


def test_of004_concurrent_area_unlock_grants_first_clear_reward_once(monkeypatch):
    sessions = [FakeSession() for _ in range(8)]
    with monkeypatch.context() as patch:
        patch.setattr(Config, "AREA_UNLOCK_REWARDS", ((102, 2),))
        responses = concurrently([
            (lambda s=s: send(area, s, AreaUnlockReq(area_id=1001), MsgId.AreaUnlockRsp))
            for s in sessions
        ])
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_OK) == 1
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_AREA_ALREADY_UNLOCK) == 7
    assert num(102) == 2
    assert db.get_claimed(1, "area_unlock") == ["1:1001"]
    assert db.get_area(1, 1, 1001)


def test_of004_area_reward_failure_rolls_back_unlock_and_claim(monkeypatch):
    session = FakeSession()
    with monkeypatch.context() as patch:
        patch.setattr(Config, "AREA_UNLOCK_REWARDS", ((102, 2),))
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(area, session, AreaUnlockReq(area_id=1001), MsgId.AreaUnlockRsp)
    assert not db.get_area(1, 1, 1001)
    assert not db.get_claimed(1, "area_unlock")
    assert num(102) == 0


def _prepare_achieve(monkeypatch):
    monkeypatch.setattr(achieve.db, "get_achieve", lambda *args: b"achieved")
    monkeypatch.setattr(achieve.achieve_track, "target_of", lambda *args: None)
    install_resources(monkeypatch, {
        "AchieveQuest": {"achieve_quest_group": {"datas": [{
            "achieve_quest_group_info": [{"achieve_condition_i_d": 501, "reward_i_d": 7001}],
        }]}},
    })
    monkeypatch.setattr(achieve, "resolve_reward", lambda *args: [(102, 3)])


def test_of005_achieve_invalid_batch_never_claims(monkeypatch):
    _prepare_achieve(monkeypatch)
    monkeypatch.setattr(achieve, "resolve_reward", lambda *args: [(102, 1), (999999999, 1)])
    session = FakeSession()
    assert send(achieve, session, GetOneAchieveAwardReq(achieve_id=501), MsgId.GetOneAchieveAwardRsp).status == StatusCode.StatusCode_CFG_NOT_FOUND
    assert not db.get_claimed(1, "achieve_one") and num(102) == 0


def test_of005_achieve_grant_failure_rolls_back_claim_and_allows_retry(monkeypatch):
    _prepare_achieve(monkeypatch)
    session = FakeSession()
    with monkeypatch.context() as patch:
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(achieve, session, GetOneAchieveAwardReq(achieve_id=501), MsgId.GetOneAchieveAwardRsp)
    assert not db.get_claimed(1, "achieve_one") and num(102) == 0
    assert send(achieve, session, GetOneAchieveAwardReq(achieve_id=501), MsgId.GetOneAchieveAwardRsp).status == StatusCode.StatusCode_OK
    assert num(102) == 3


def test_of005_concurrent_achieve_claim_grants_once(monkeypatch):
    _prepare_achieve(monkeypatch)
    sessions = [FakeSession() for _ in range(8)]
    responses = concurrently([
        (lambda s=s: send(achieve, s, GetOneAchieveAwardReq(achieve_id=501), MsgId.GetOneAchieveAwardRsp))
        for s in sessions
    ])
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_OK) == 1
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_REPEAT_GET_REWARD) == 7
    assert num(102) == 3


def _prepare_collection_reward(monkeypatch):
    install_resources(monkeypatch, {**res_loader.res, **collection_resources()})
    monkeypatch.setattr(collection_reward, "resolve_reward", lambda *args: [(102, 4)])
    db.set_collection(1, 9001, 1, PBCollectionRewardData(item_id=9001, status=RewardStatus.NotReward).SerializeToString())


def test_of005_collection_reward_failure_rolls_back_claim_and_status(monkeypatch):
    _prepare_collection_reward(monkeypatch)
    session = FakeSession()
    with monkeypatch.context() as patch:
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(collection_reward, session, CollectionRewardReq(item_id=9001), MsgId.CollectionRewardRsp)
    assert not db.get_claimed(1, "collection")
    assert PBCollectionRewardData.FromString(db.get_collection(1, 9001)[1]).status == RewardStatus.NotReward
    assert num(102) == 0
    assert send(collection_reward, session, CollectionRewardReq(item_id=9001), MsgId.CollectionRewardRsp).status == StatusCode.StatusCode_OK
    assert num(102) == 4


def test_of005_concurrent_collection_reward_grants_once(monkeypatch):
    _prepare_collection_reward(monkeypatch)
    sessions = [FakeSession() for _ in range(8)]
    responses = concurrently([
        (lambda s=s: send(collection_reward, s, CollectionRewardReq(item_id=9001), MsgId.CollectionRewardRsp))
        for s in sessions
    ])
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_OK) == 1
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_COLLECTION_ALREADY_REWARDED) == 7
    assert num(102) == 4


def test_of005_badge_invalid_batch_never_writes_claims(monkeypatch):
    install_resources(monkeypatch, badge_resources(item_id=999999999))
    monkeypatch.setattr(badge.achieve_track, "target_of", lambda *args: None)
    session = FakeSession()
    rsp = send(badge, session, AbilityBadgeAchieveRewardReq(achieve_ids=[501]), MsgId.AbilityBadgeAchieveRewardRsp)
    assert rsp.status == StatusCode.StatusCode_CFG_NOT_FOUND
    assert not db.get_claimed(1, "badge_achieve") and not rsp.items


def test_of005_collection_invalid_batch_preserves_status_and_claim(monkeypatch):
    _prepare_collection_reward(monkeypatch)
    monkeypatch.setattr(collection_reward, "resolve_reward", lambda *args: [(102, 1), (999999999, 1)])
    session = FakeSession()
    rsp = send(collection_reward, session, CollectionRewardReq(item_id=9001), MsgId.CollectionRewardRsp)
    assert rsp.status == StatusCode.StatusCode_CFG_NOT_FOUND
    assert not db.get_claimed(1, "collection") and num(102) == 0
    assert PBCollectionRewardData.FromString(db.get_collection(1, 9001)[1]).status == RewardStatus.NotReward


def test_of005_badge_batch_failure_rolls_back_every_claim(monkeypatch):
    install_resources(monkeypatch, {**res_loader.res, **badge_resources()})
    monkeypatch.setattr(badge.achieve_track, "target_of", lambda *args: None)
    session = FakeSession()
    req = AbilityBadgeAchieveRewardReq(achieve_ids=[501, 501])
    with monkeypatch.context() as patch:
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(badge, session, req, MsgId.AbilityBadgeAchieveRewardRsp)
    assert not db.get_claimed(1, "badge_achieve") and num(102) == 0
    assert send(badge, session, req, MsgId.AbilityBadgeAchieveRewardRsp).status == StatusCode.StatusCode_OK
    assert num(102) == 1 and list(rsp.achieve_ids for rsp in [session.response(MsgId.AbilityBadgeAchieveRewardRsp)]) == [[501]]


def test_of005_concurrent_badge_claim_grants_once(monkeypatch):
    install_resources(monkeypatch, {**res_loader.res, **badge_resources()})
    monkeypatch.setattr(badge.achieve_track, "target_of", lambda *args: None)
    sessions = [FakeSession() for _ in range(8)]
    req = AbilityBadgeAchieveRewardReq(achieve_ids=[501])
    responses = concurrently([
        (lambda s=s: send(badge, s, req, MsgId.AbilityBadgeAchieveRewardRsp)) for s in sessions
    ])
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_OK) == 1
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_ABILITY_BADGE_ACHIEVE_REWARDED) == 7
    assert num(102) == 1


def test_of006_item_sweep_rejects_zero_count_without_side_effects(monkeypatch):
    grant(Config.VITALITY_ITEM_ID, 2)
    session = FakeSession()
    with monkeypatch.context() as patch:
        install_resources(patch, quick_resources())
        rsp = send(item_sweep, session, ItemSweepReq(item_id=102, count=0, is_sweep=True), MsgId.ItemSweepRsp)
    assert rsp.status == StatusCode.StatusCode_BAD_REQ
    assert num(Config.VITALITY_ITEM_ID) == 2 and num(102) == 0


def test_of006_item_sweep_overflow_is_rejected_before_debit(monkeypatch):
    grant(Config.VITALITY_ITEM_ID, 100)
    session = FakeSession()
    resources = quick_resources(vitality=Config.ECONOMY_ITEM_NUM_MAX)
    with monkeypatch.context() as patch:
        install_resources(patch, resources)
        rsp = send(item_sweep, session, ItemSweepReq(item_id=102, count=2, is_sweep=True), MsgId.ItemSweepRsp)
    assert rsp.status == StatusCode.StatusCode_CFG_NOT_FOUND
    assert num(Config.VITALITY_ITEM_ID) == 100 and num(102) == 0


def test_of006_item_sweep_failure_rolls_back_cost_and_reward(monkeypatch):
    grant(Config.VITALITY_ITEM_ID, 2)
    session = FakeSession()
    with monkeypatch.context() as patch:
        install_resources(patch, quick_resources())
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(item_sweep, session, ItemSweepReq(item_id=102, count=1, is_sweep=True), MsgId.ItemSweepRsp)
    assert num(Config.VITALITY_ITEM_ID) == 2 and num(102) == 0
    with monkeypatch.context() as patch:
        install_resources(patch, quick_resources())
        assert send(item_sweep, session, ItemSweepReq(item_id=102, count=1, is_sweep=True), MsgId.ItemSweepRsp).status == StatusCode.StatusCode_OK
    assert num(Config.VITALITY_ITEM_ID) == 0 and num(102) == 1


def _dungeon_resources(cost=2):
    return {"Dungeon": {"dungeon": {"datas": [{
        "i_d": 88001, "is_can_sweep": True, "item_i_d": Config.VITALITY_ITEM_ID,
        "item_num": cost, "reward_i_d": 7001,
    }]}}}


def test_of006_dungeon_sweep_failure_rolls_back_cost_and_finish_count(monkeypatch):
    grant(Config.VITALITY_ITEM_ID, 2)
    session = FakeSession()
    with monkeypatch.context() as patch:
        install_resources(patch, {**res_loader.res, **_dungeon_resources()})
        patch.setattr(dungeon_sweep, "resolve_drop", lambda *args: [(102, 2)])
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(dungeon_sweep, session, DungeonSweepReq(dungeon_id=88001), MsgId.DungeonSweepRsp)
    assert num(Config.VITALITY_ITEM_ID) == 2 and num(102) == 0
    assert db.get_dungeon(1, 88001) is None


def test_of006_dungeon_cost_multiplication_overflow_is_rejected(monkeypatch):
    grant(Config.VITALITY_ITEM_ID, 100)
    session = FakeSession()
    resources = _dungeon_resources(cost=Config.ECONOMY_ITEM_NUM_MAX)
    resources["Dungeon"]["dungeon"]["datas"][0]["new_mission_type"] = Config.MATERIAL_DUNGEON_TYPE
    with monkeypatch.context() as patch:
        install_resources(patch, {**res_loader.res, **resources})
        patch.setattr(dungeon_sweep, "reward_multiplier", lambda *args: 2)
        rsp = send(dungeon_sweep, session, DungeonSweepReq(dungeon_id=88001), MsgId.DungeonSweepRsp)
    assert rsp.status == StatusCode.StatusCode_CFG_NOT_FOUND
    assert num(Config.VITALITY_ITEM_ID) == 100 and db.get_dungeon(1, 88001) is None


def test_of006_concurrent_dungeon_sweeps_do_not_lose_finish_count(monkeypatch):
    grant(Config.VITALITY_ITEM_ID, 16)
    sessions = [FakeSession() for _ in range(8)]
    with monkeypatch.context() as patch:
        install_resources(patch, {**res_loader.res, **_dungeon_resources()})
        patch.setattr(dungeon_sweep, "resolve_drop", lambda *args: [(102, 2)])
        responses = concurrently([
            (lambda s=s: send(dungeon_sweep, s, DungeonSweepReq(dungeon_id=88001), MsgId.DungeonSweepRsp))
            for s in sessions
        ])
    assert all(rsp.status == StatusCode.StatusCode_OK for rsp in responses)
    assert num(Config.VITALITY_ITEM_ID) == 0 and num(102) == 16
    from proto.net_pb2 import DungeonData
    assert DungeonData.FromString(db.get_dungeon(1, 88001)).finish_times == 8


def _prepare_dig(monkeypatch):
    install_resources(monkeypatch, {
        **res_loader.res,
        "Treasure": {"treasure": {"datas": [{"i_d": 5070001}]}},
        "Shovel": {"shovel": {"datas": [{"item_i_d": 11, "success_rate": 1000}]}},
    })
    monkeypatch.setattr(Config, "DIG_POOLS", {5070001: (7001,)})
    monkeypatch.setattr(Config, "FAIL_POOL", 7002)
    monkeypatch.setattr(treasure_dig, "resolve_reward", lambda *args: [(102, 4)])
    grant(11, 1)
    grant(5070001, 1)
    assert num(11) == 1 and has_treasure_map()


def test_of006_treasure_dig_failure_rolls_back_map_and_reward(monkeypatch):
    _prepare_dig(monkeypatch)
    session = FakeSession()
    with monkeypatch.context() as patch:
        patch.setattr(item_mgr, "grant_items", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("grant failed")))
        with pytest.raises(RuntimeError, match="grant failed"):
            send(treasure_dig, session, TreasureDigReq(treasure_id=5070001), MsgId.TreasureDigRsp)
    assert has_treasure_map() and num(102) == 0
    assert db.get_kv(1, "archaeology", "102", 0) == 0


def test_of006_concurrent_treasure_digs_debit_each_map_once(monkeypatch):
    _prepare_dig(monkeypatch)
    sessions = [FakeSession() for _ in range(8)]
    responses = concurrently([
        (lambda s=s: send(treasure_dig, s, TreasureDigReq(treasure_id=5070001), MsgId.TreasureDigRsp))
        for s in sessions
    ])
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_OK) == 1
    assert [rsp.status for rsp in responses].count(StatusCode.StatusCode_ITEM_NOT_ENOUGH) == 7
    assert not has_treasure_map() and num(102) == 4
    assert db.get_kv(1, "archaeology", "102", 0) == 1
