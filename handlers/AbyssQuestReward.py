from network.msg_id import MsgId
from network.packet_handler import PacketHandler, packet_handler
from proto.net_pb2 import AbyssQuestRewardReq, AbyssQuestRewardRsp, StatusCode
from server import abyss
from utils import item_mgr
from utils.reward_resolver import resolve_reward
import utils.db as db


def _player_level(player_id):
    row = db.get_players_info(player_id, "level")
    return int(row[0]) if row else 0


@packet_handler(MsgId.AbyssQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbyssQuestRewardReq()
        req.ParseFromString(data)
        rsp = AbyssQuestRewardRsp()
        season_data = abyss.season(req.season_id)
        reward_id = abyss.reward_config(season_data, req.condition_id)
        if reward_id is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.AbyssQuestRewardRsp, rsp, packet_id)
            return
        claim_key = f"{req.season_id}:{req.condition_id}"
        with abyss.lock, item_mgr.player_lock(session.player_id), db.transaction():
            if not abyss.achievement_met(session.player_id, season_data, req.condition_id):
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.AbyssQuestRewardRsp, rsp, packet_id)
                return
            if not db.try_claim(session.player_id, "abyss_quest", claim_key):
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                session.send(MsgId.AbyssQuestRewardRsp, rsp, packet_id)
                return
            rewards = tuple(resolve_reward(reward_id, _player_level(session.player_id)) or ())
            if not rewards:
                db.rollback_claim(session.player_id, "abyss_quest", claim_key)
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.AbyssQuestRewardRsp, rsp, packet_id)
                return
            try:
                item_mgr.validate_rewards(rewards)
                item_mgr.grant_items(session.player_id, rewards, rsp_items=rsp.rewards, session=None)
            except Exception:
                db.rollback_claim(session.player_id, "abyss_quest", claim_key)
                raise
        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.AbyssQuestRewardRsp, rsp, packet_id)
