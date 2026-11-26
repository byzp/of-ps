from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import BossRushQuestRewardReq, BossRushQuestRewardRsp, StatusCode
from server import boss_rush
from utils.res_loader import res
from utils import item_mgr
from utils.reward_resolver import resolve_reward
import utils.db as db


def _player_level(player_id):
    row = db.get_players_info(player_id, "level")
    return int(row[0]) if row else 0


def _reward_config(season_id, achieve_id):
    season_data = boss_rush.season(season_id)
    if not season_data:
        return None
    table_id = season_data.get("season_achieve")
    for entry in res.get("BossRush", {}).get("boss_rush_achieve", {}).get("datas", ()):
        if entry.get("i_d") != table_id:
            continue
        group = next(
            (row for row in entry.get("boss_rush_achieve_group_info", ()) if row.get("achieve_i_d") == achieve_id),
            None,
        )
        if group:
            return group.get("reward_i_d")
    return None


def _threshold(achieve_id):
    row = next(
        (row for row in res.get("Achieve", {}).get("achieve", {}).get("datas", ()) if row.get("i_d") == achieve_id),
        None,
    )
    if not row or int(row.get("new_achieve_condition", 0) or 0) != 178:
        return None
    threshold = int(row.get("count_param", 0) or 0)
    return threshold if threshold > 0 else None


@packet_handler(MsgId.BossRushQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushQuestRewardReq()
        req.ParseFromString(data)
        rsp = BossRushQuestRewardRsp(season_id=req.season_id, achieve_id=req.achieve_id)
        reward_id = _reward_config(req.season_id, req.achieve_id)
        threshold = _threshold(req.achieve_id)
        season_data = boss_rush.season(req.season_id)
        if reward_id is None or threshold is None or season_data is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)
            return

        claim_key = f"{req.season_id}:{req.achieve_id}"
        with boss_rush.lock, item_mgr.player_lock(session.player_id), db.transaction():
            info, run, dirty = boss_rush.load_state(session.player_id, season_data)
            if dirty:
                boss_rush.save_state(session.player_id, req.season_id, info, run)
            if info.best_total_score < threshold:
                rsp.status = StatusCode.StatusCode_BAD_REQ
                session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)
                return
            if not db.try_claim(session.player_id, "boss_rush_quest", claim_key):
                rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
                session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)
                return
            rewards = tuple(resolve_reward(reward_id, _player_level(session.player_id)) or ())
            if not rewards:
                db.rollback_claim(session.player_id, "boss_rush_quest", claim_key)
                rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
                session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)
                return
            try:
                item_mgr.validate_rewards(rewards)
                item_mgr.grant_items(session.player_id, rewards, rsp_items=rsp.rewards, session=None)
            except Exception:
                db.rollback_claim(session.player_id, "boss_rush_quest", claim_key)
                raise

        rsp.status = StatusCode.StatusCode_OK
        session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)
