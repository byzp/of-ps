from config import Config
from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import DungeonStarRewardReq, DungeonStarRewardRsp, DungeonData, PackNotice, RewardStatus, StatusCode
from server import abyss
from utils import item_mgr
import utils.db as db


@packet_handler(MsgId.DungeonStarRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = DungeonStarRewardReq()
        req.ParseFromString(data)
        rsp = DungeonStarRewardRsp()
        if not req.dungeon_id or abyss.dungeon(req.dungeon_id) is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonStarRewardRsp, rsp, packet_id)
            return
        rewards = tuple(Config.DUNGEON_STAR_REWARDS.get(req.dungeon_id, ()) or ())
        if not rewards:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.DungeonStarRewardRsp, rsp, packet_id)
            return
        claim_key = f"{req.dungeon_id}"
        notice = PackNotice(status=StatusCode.StatusCode_OK)
        with item_mgr.player_lock(session.player_id), db.transaction():
            blob = db.get_dungeon(session.player_id, req.dungeon_id)
            dg = DungeonData()
            if blob:
                dg.ParseFromString(blob)
            if dg.dungeon_id != req.dungeon_id or dg.finish_times <= 0 or dg.star_reward == RewardStatus.Reward:
                rsp.status = StatusCode.StatusCode_BAD_REQ if dg.finish_times <= 0 else StatusCode.StatusCode_REPEAT_GET_REWARD
            elif not db.try_claim(session.player_id, "dungeon_star", claim_key):
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            else:
                try:
                    item_mgr.validate_rewards(rewards)
                    item_mgr.grant_items(
                        session.player_id, rewards, rsp_items=rsp.rewards,
                        pack_notice=notice, session=None,
                    )
                except Exception:
                    db.rollback_claim(session.player_id, "dungeon_star", claim_key)
                    raise
                dg.star_reward = RewardStatus.Reward
                db.set_dungeon(session.player_id, req.dungeon_id, dg.SerializeToString())
                rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.DungeonStarRewardRsp, rsp, packet_id)
        if rsp.status == StatusCode.StatusCode_OK:
            session.send(MsgId.PackNotice, notice, 0)
