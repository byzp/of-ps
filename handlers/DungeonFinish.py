from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import DungeonData, DungeonFinishReq, DungeonFinishRsp, PackNotice, StatusCode
import utils.db as db
from utils import achieve_track, item_mgr
from utils.dungeon_reward import dungeon_config
from utils.reward_resolver import resolve_drop


def _first_clear_rewards(cfg, world_level, player_level):
    reward_id = cfg.get("reward_i_d", 0)
    if not reward_id or reward_id == Config.NONE_REWARD:
        return []
    rewards = resolve_drop(reward_id, world_level, player_level)
    if not rewards:
        raise item_mgr.EconomyConfigError("missing dungeon first-clear reward config")
    item_mgr.validate_rewards(rewards)
    return rewards


@packet_handler(MsgId.DungeonFinishReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        DungeonFinishReq().ParseFromString(data)
        rsp = DungeonFinishRsp()
        dungeon_id = session.dungeon[0]
        token = getattr(session, "dungeon_token", "")
        if not dungeon_id or not token:
            rsp.status = StatusCode.StatusCode_PlayerNotInDungeon
            session.send(MsgId.DungeonFinishRsp, rsp, packet_id)
            return
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        cfg = None
        # 同一玩家的重复 Finish 在锁内先被原子去重; 奖励、首通状态和领奖标记
        # 的后续写入处于同一事务, 任一失败均撤销预领标记。
        with item_mgr.player_lock(session.player_id):
            if not db.try_claim(session.player_id, "dungeon_finish", token):
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            else:
                try:
                    with db.transaction():
                        cfg = self._settle(session, dungeon_id, rsp, notice)
                except item_mgr.EconomyConfigError:
                    db.rollback_claim(session.player_id, "dungeon_finish", token)
                    rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                    del rsp.rewards[:]
                    del notice.items[:]
                except Exception:
                    db.rollback_claim(session.player_id, "dungeon_finish", token)
                    raise
                if rsp.status != StatusCode.StatusCode_OK:
                    db.rollback_claim(session.player_id, "dungeon_finish", token)
        session.send(MsgId.DungeonFinishRsp, rsp, packet_id)
        if rsp.status != StatusCode.StatusCode_OK:
            return
        with achieve_track.batch(session):
            achieve_track.report(
                session,
                "dungeon_finish",
                match=dungeon_id,
                mission_type=cfg.get("new_mission_type") if cfg else None,
            )
        if notice.items:
            session.send(MsgId.PackNotice, notice, 0)

    @staticmethod
    def _settle(session, dungeon_id, rsp, notice):
        cfg = dungeon_config(dungeon_id)
        blob = db.get_dungeon(session.player_id, dungeon_id)
        if not blob:
            rsp.status = StatusCode.StatusCode_PlayerNotInDungeon
            return cfg
        if cfg is None:
            raise item_mgr.EconomyConfigError("missing dungeon config")
        dungeon = DungeonData.FromString(blob)
        if dungeon.dungeon_id and dungeon.dungeon_id != dungeon_id:
            raise item_mgr.EconomyConfigError("dungeon state id mismatch")
        finish_times = item_mgr.validate_counter(
            dungeon.finish_times, label="dungeon finish count"
        )
        if finish_times == Config.ECONOMY_UINT32_MAX:
            rsp.status = StatusCode.StatusCode_BAD_REQ
            return cfg
        rewards = []
        if finish_times == 0:
            level_row = db.get_players_info(session.player_id, "level")
            world_row = db.get_players_info(session.player_id, "world_level")
            rewards = _first_clear_rewards(
                cfg,
                int(world_row[0] or 1) if world_row else 1,
                int(level_row[0] or 1) if level_row else 1,
            )
        if rewards:
            item_mgr.grant_items(
                session.player_id,
                rewards,
                rsp_items=rsp.rewards,
                pack_notice=notice,
                session=session,
            )
        dungeon.finish_times = item_mgr.checked_add(
            finish_times, 1, limit=Config.ECONOMY_UINT32_MAX
        )
        db.set_dungeon(session.player_id, dungeon_id, dungeon.SerializeToString())
        rsp.dungeon_data.CopyFrom(dungeon)
        rsp.scene_id = session.scene_id
        rsp.status = StatusCode.StatusCode_OK
        return cfg
