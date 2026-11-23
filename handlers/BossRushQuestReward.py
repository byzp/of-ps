from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    BossRushQuestRewardReq,
    BossRushQuestRewardRsp,
    StatusCode,
)

from utils.res_loader import res
from utils import item_mgr
from utils.reward_resolver import resolve_reward
import utils.db as db


def _player_level(player_id):
    row = db.get_players_info(player_id, "level")
    return row[0] if row else 0


"""
# BossRush 赛季成就领奖 2717 2718
奖励链路(已对表验证): BossRush.boss_rush_season.season_achieve -> BossRush.boss_rush_achieve
.boss_rush_achieve_group_info{achieve_i_d, reward_i_d} -> Reward.reward_pool
(如 season 1001 achieve 18100101 -> reward 5050101 -> 联合演算补给箱x2 等)。
领取状态经 db.try_claim 去重(claime d_rewards 表)
"""


@packet_handler(MsgId.BossRushQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = BossRushQuestRewardReq()
        req.ParseFromString(data)

        rsp = BossRushQuestRewardRsp()
        rsp.season_id = req.season_id
        rsp.achieve_id = req.achieve_id

        achieve_table_id = req.season_id
        reward_id = None
        _br = res.get("BossRush") if isinstance(res.get("BossRush"), dict) else {}
        _seasons = (
            _br.get("boss_rush_season", {}).get("datas")
            if isinstance(_br.get("boss_rush_season"), dict)
            else None
        )
        _achieves = (
            _br.get("boss_rush_achieve", {}).get("datas")
            if isinstance(_br.get("boss_rush_achieve"), dict)
            else None
        )
        if isinstance(_seasons, (list, tuple)):
            for season in _seasons:
                if isinstance(season, dict) and season.get("i_d") == req.season_id:
                    achieve_table_id = season.get("season_achieve", req.season_id)
                    break
        if isinstance(_achieves, (list, tuple)):
            for entry in _achieves:
                if isinstance(entry, dict) and entry.get("i_d") == achieve_table_id:
                    for g in entry.get("boss_rush_achieve_group_info") or ():
                        if g.get("achieve_i_d") == req.achieve_id:
                            reward_id = g.get("reward_i_d")
                            break
                    break

        if reward_id is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)
            return

        if not db.try_claim(
            session.player_id, "boss_rush_quest", f"{req.season_id}:{req.achieve_id}"
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        reward_list = resolve_reward(reward_id, _player_level(session.player_id))
        item_mgr.grant_items(
            session.player_id, reward_list, rsp_items=rsp.rewards, session=session
        )

        session.send(MsgId.BossRushQuestRewardRsp, rsp, packet_id)  # 2717,2718
