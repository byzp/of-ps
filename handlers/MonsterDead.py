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
from config import Config


def _monster_reward_id(monster_id):
    """Monster.json monster_character_data.reward_pool_i_d(仅少数首领怪配置,
    如 9007->3010371 / 9010->3010971, 其余怪物无个体掉落)"""
    for e in res.get("Monster", {}).get("monster_character_data", {}).get("datas", ()):
        if e.get("i_d") == monster_id:
            return e.get("reward_pool_i_d", 0)
    return 0


def _monster_tag(monster_id):
    """Monster.json monster_character_data.new_tag(3=BOSS)。"""
    for e in res.get("Monster", {}).get("monster_character_data", {}).get("datas", ()):
        if e.get("i_d") == monster_id:
            return e.get("new_tag", 0)
    return 0


@packet_handler(MsgId.MonsterDeadReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = MonsterDeadReq()
        req.ParseFromString(data)

        rsp = MonsterDeadRsp()
        rsp.status = StatusCode.StatusCode_OK
        rsp.monster_index = req.monster_index

        reward_id = _monster_reward_id(req.monster_id)
        world_level = db.get_players_info(session.player_id, "world_level")[0]
        player_level = db.get_players_info(session.player_id, "level")[0]
        reward_list = (
            resolve_drop(reward_id, world_level, player_level) if reward_id else []
        )
        drops = [
            make_item(item_id, count, session.player_id)
            for item_id, count in reward_list
        ]
        world_drops = (
            session.scene_id != Config.TUTORIAL_SCENE_ID
            and _scene_types().get(session.scene_id) != Config.INSTANCE_SCENE_TYPE
        )
        if not reward_id and world_drops:
            drops = monster_loot.roll(session.player_id, player_level, world_level)

        with achieve_track.batch(session):
            # 成就: 击杀事件一次上报, 模块内部扫表记录该怪的全部讨伐/排除成就
            # (讨伐1/4/6/41/42 + 全局86 + 按世界106), 有掉落的首领怪同样计入
            achieve_track.report(
                session,
                "kill",
                match=req.monster_id,
                monster_tag=_monster_tag(req.monster_id),
            )
            if drops:
                # 击杀只生成待领取掉落；实例号在此分配，领取时才入包。
                rsp.drop_item.index = db.incr_kv(session.player_id, "drop", "seq")
                for item in drops:
                    item.pack_type = ItemDetail.PackType.PackType_TempStorageArea
                    rsp.drop_item.items.add().CopyFrom(item)
                with session.drop_lock:
                    session.drop_items[rsp.drop_item.index] = [
                        item.SerializeToString() for item in rsp.drop_item.items
                    ]
            session.send(MsgId.MonsterDeadRsp, rsp, packet_id)
            if (
                world_drops
                and db.has_unlock_function(
                    session.player_id, Config.DAILY_TASK_UNLOCK_FUNCTION_ID
                )
                and random.random() < Config.MOON_KILL_REWARD_CHANCE
            ):
                # 直接入包的祈愿碎片与等待拾取的装备掉落彼此独立。
                notice = MoonQuestGamePlayRewardNotice(
                    status=StatusCode.StatusCode_OK,
                    id=Config.MOON_KILL_REWARD_SOURCE_ID,
                )
                pack = PackNotice(status=StatusCode.StatusCode_OK)
                rewards = resolve_reward(Config.MOON_KILL_REWARD_POOL, player_level)
                item_mgr.grant_items(
                    session.player_id,
                    rewards,
                    rsp_items=notice.rewards,
                    pack_notice=pack,
                    session=session,
                )
                session.send(MsgId.MoonQuestGamePlayRewardNotice, notice, 0)
                if pack.items:
                    session.send(MsgId.PackNotice, pack, 0)
