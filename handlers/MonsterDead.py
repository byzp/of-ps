from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    MonsterDeadReq,
    MonsterDeadRsp,
    StatusCode,
    ItemDetail,
    PackNotice,
    MoonQuestGamePlayRewardNotice,
)
import random

import utils.db as db
from utils.pb_create import make_item, _scene_types
from utils.res_loader import res
from utils.reward_resolver import resolve_drop, resolve_reward
from utils import achieve_track, item_mgr
from utils import monster_loot
from utils import dungeon_state
from config import Config


def _monster_config(monster_id):
    for entry in res.get("Monster", {}).get("monster_character_data", {}).get("datas", ()):
        if entry.get("i_d") == monster_id:
            return entry
    return None


def _monster_reward_id(monster_id):
    entry = _monster_config(monster_id)
    return entry.get("reward_pool_i_d", 0) if entry else 0


def _monster_tag(monster_id):
    entry = _monster_config(monster_id)
    return entry.get("new_tag", 0) if entry else 0


def _run_token(session, monster_index, monster_id):
    """只接受服务端会话为具体怪物实例签发的 token; 客户端无法设置映射。

    世界场景目前没有权威怪物状态, 因而默认拒绝。场景管理器以后可通过
    session.world_monster_tokens[(scene_id, index, unit_id)] 注入实例 token,
    无需改协议即可接入; 标量 run token 不能证明客户端提交的怪物实例存在。
    """
    if session.dungeon[0]:
        return getattr(session, "dungeon_token", "")
    tokens = getattr(session, "world_monster_tokens", None)
    if not isinstance(tokens, dict):
        return ""
    return tokens.get((session.scene_id, monster_index, monster_id), "")


def _dungeon_monster_id(session, monster_index):
    config = next(
        (
            row
            for row in res["ScenesConfigAsset"]["Dungeons"]
            if row["ID"] == session.dungeon[0]
        ),
        None,
    )
    points = (
        (row["Index"], row["UnitID"])
        for row in (config.get("MonsterInfos", ()) if config else ())
    )
    return next((unit_id for index, unit_id in points if index == monster_index), None)


@packet_handler(MsgId.MonsterDeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        with item_mgr.player_lock(session.player_id):
            self._handle(session, data, packet_id)

    def _handle(self, session, data: bytes, packet_id: int):
        req = MonsterDeadReq()
        req.ParseFromString(data)

        rsp = MonsterDeadRsp()
        rsp.monster_index = req.monster_index
        try:
            item_mgr.validate_counter(req.monster_id, allow_zero=False, label="monster id")
            item_mgr.validate_counter(
                req.monster_index, allow_zero=True, label="monster index"
            )
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            session.send(MsgId.MonsterDeadRsp, rsp, packet_id)
            return

        # 没有权威战斗状态时必须 fail closed, 不能按客户端 ID 发固定奖励。
        token = _run_token(session, req.monster_index, req.monster_id)
        if not token or not _monster_config(req.monster_id):
            rsp.status = StatusCode.StatusCode_FAIL
            session.send(MsgId.MonsterDeadRsp, rsp, packet_id)
            return

        # 副本点位必须使用服务端配置的怪物, 防止同一点位替换成首领奖励池。
        if session.dungeon[0]:
            expected_id = _dungeon_monster_id(session, req.monster_index)
            if expected_id is not None and expected_id != req.monster_id:
                rsp.status = StatusCode.StatusCode_FAIL
                session.send(MsgId.MonsterDeadRsp, rsp, packet_id)
                return
            if expected_id is None and _monster_tag(req.monster_id) == 3:
                rsp.status = StatusCode.StatusCode_FAIL
                session.send(MsgId.MonsterDeadRsp, rsp, packet_id)

        claim_key = (
            f"{session.scene_id}:{session.dungeon[0]}:{token}:"
            f"{req.monster_index}:{req.monster_id}"
        )
        world_level = db.get_players_info(session.player_id, "world_level")[0]
        player_level = db.get_players_info(session.player_id, "level")[0]
        reward_id = _monster_reward_id(req.monster_id)
        reward_list = resolve_drop(reward_id, world_level, player_level) if reward_id else []
        item_mgr.validate_rewards(reward_list)

        notice = PackNotice(status=StatusCode.StatusCode_OK)
        moon_notice = None
        moon_rewards = []
        staged_drops = None
        drop_index = 0
        try:
            # claim、掉落实例号、直接奖励处于同一事务; 通知在提交后执行。
            with item_mgr.deferred_notifications(), db.transaction():
                if not db.try_claim(session.player_id, "monster_kill", claim_key):
                    rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                else:
                    drops = [
                        make_item(item_id, count, session.player_id)
                        for item_id, count in reward_list
                    ]
                    world_drops = (
                        not session.dungeon[0]
                        and session.scene_id != Config.TUTORIAL_SCENE_ID
                        and _scene_types().get(session.scene_id) != Config.INSTANCE_SCENE_TYPE
                    )
                    if not reward_id and world_drops:
                        drops = monster_loot.roll(
                            session.player_id, player_level, world_level
                        )
                    if drops:
                        drop_index = db.incr_kv(session.player_id, "drop", "seq")
                        staged_drops = []
                        for item in drops:
                            item.pack_type = ItemDetail.PackType.PackType_TempStorageArea
                            staged_drops.append(item.SerializeToString())
                            rsp.drop_item.items.add().CopyFrom(item)
                        rsp.drop_item.index = drop_index

                    if (
                        world_drops
                        and db.has_unlock_function(
                            session.player_id, Config.DAILY_TASK_UNLOCK_FUNCTION_ID
                        )
                        and random.random() < Config.MOON_KILL_REWARD_CHANCE
                    ):
                        moon_notice = MoonQuestGamePlayRewardNotice(
                            status=StatusCode.StatusCode_OK,
                            id=Config.MOON_KILL_REWARD_SOURCE_ID,
                        )
                        moon_rewards = resolve_reward(
                            Config.MOON_KILL_REWARD_POOL, player_level
                        )
                        item_mgr.validate_rewards(moon_rewards)
                        item_mgr.grant_items(
                            session.player_id,
                            moon_rewards,
                            rsp_items=moon_notice.rewards,
                            pack_notice=notice,
                            session=session,
                        )
                    rsp.status = StatusCode.StatusCode_OK
        except item_mgr.EconomyConfigError:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            del rsp.drop_item.items[:]
            rsp.drop_item.index = 0
            notice.ClearField("items")
            moon_notice = None

        # 会话临时掉落只在事务成功后发布, 失败不会留下可拾取实例。
        if staged_drops is not None and rsp.status == StatusCode.StatusCode_OK:
            with session.drop_lock:
                session.drop_items[drop_index] = staged_drops
        session.send(MsgId.MonsterDeadRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        with achieve_track.batch(session):
            dungeon_state.record_monster(
                session, req.monster_index, req.monster_id, _monster_tag(req.monster_id)
            )
            achieve_track.report(
                session,
                "kill",
                match=req.monster_id,
                monster_tag=_monster_tag(req.monster_id),
            )
        if moon_notice is not None:
            session.send(MsgId.MoonQuestGamePlayRewardNotice, moon_notice, 0)
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)
