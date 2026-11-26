from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import DungeonTaskFinishRewardReq, DungeonTaskFinishRewardRsp, DungeonData, PackNotice, RewardStatus, StatusCode
from server import abyss
from utils import item_mgr
from utils.reward_resolver import resolve_drop
import utils.db as db


def _player_values(player_id):
    level_row = db.get_players_info(player_id, "level")
    world_row = db.get_players_info(player_id, "world_level")
    level = int(level_row[0]) if level_row else 0
    world_level = int(world_row[0]) if world_row else 0
    return level, world_level


@packet_handler(MsgId.DungeonTaskFinishRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonTaskFinishRewardReq()
        req.ParseFromString(data)
        rsp = DungeonTaskFinishRewardRsp()
        config = abyss.dungeon(req.dungeon_id) if req.dungeon_id else None
        reward_id = int((config or {}).get("reward_i_d", 0) or 0)
        if config is None or not reward_id:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonTaskFinishRewardRsp, rsp, packet_id)
            return
        level, world_level = _player_values(session.player_id)
        rewards = tuple(resolve_drop(reward_id, world_level, level) or ())
        if not rewards:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonTaskFinishRewardRsp, rsp, packet_id)
            return
        claim_key = f"{req.dungeon_id}"
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        with item_mgr.player_lock(session.player_id), db.transaction():
            blob = db.get_dungeon(session.player_id, req.dungeon_id)
            dg = DungeonData()
            if blob:
                dg.ParseFromString(blob)
            if dg.dungeon_id != req.dungeon_id or dg.finish_times <= 0 or not dg.all_task_finished:
                rsp.status = StatusCode.StatusCode_BAD_REQ
            elif dg.task_finish_reward == RewardStatus.Reward:
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            elif not db.try_claim(session.player_id, "dungeon_task", claim_key):
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            else:
                try:
                    item_mgr.validate_rewards(rewards)
                    item_mgr.grant_items(
                        session.player_id, rewards, rsp_items=rsp.rewards,
                        pack_notice=notice, session=None,
                    )
                except Exception:
                    db.rollback_claim(session.player_id, "dungeon_task", claim_key)
                    raise
                dg.task_finish_reward = RewardStatus.Reward
                db.set_dungeon(session.player_id, req.dungeon_id, dg.SerializeToString())
                rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.DungeonTaskFinishRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            session.send(MsgId.PackNotice, notice, 0)
