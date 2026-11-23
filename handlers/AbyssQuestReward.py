from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import AbyssQuestRewardReq, AbyssQuestRewardRsp, StatusCode

from utils.res_loader import res
from utils import item_mgr
from utils.reward_resolver import resolve_reward
import utils.db as db


def _player_level(player_id):
    row = db.get_players_info(player_id, "level")
    return row[0] if row else 0


"""
# 深渊赛季成就领奖 2113 2114
奖励链路(已对表验证): Abyss.abyss_season.season_achieve -> Abyss.season_achieve
.season_achieve_group_info{achieve_i_d, reward_i_d} -> Reward.reward_pool
(如 season 1 achieve 17010001 -> reward 5010010 -> 金币x2000/大瓶能量饮料x2 等)。
领取状态经 db.try_claim 去重(claime d_rewards 表)
"""


@packet_handler(MsgId.AbyssQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = AbyssQuestRewardReq()
        req.ParseFromString(data)

        rsp = AbyssQuestRewardRsp()

        # abyss_season.i_d -> season_achieve 表 i_d -> 条目 achieve_i_d == condition_id
        reward_id = None
        _ab = res.get("Abyss") if isinstance(res.get("Abyss"), dict) else {}
        _seasons = (
            _ab.get("abyss_season", {}).get("datas")
            if isinstance(_ab.get("abyss_season"), dict)
            else None
        )
        _achieves = (
            _ab.get("season_achieve", {}).get("datas")
            if isinstance(_ab.get("season_achieve"), dict)
            else None
        )
        achieve_table_id = None
        if isinstance(_seasons, (list, tuple)):
            for s in _seasons:
                if isinstance(s, dict) and s.get("i_d") == req.season_id:
                    achieve_table_id = s.get("season_achieve")
                    break
        if isinstance(_achieves, (list, tuple)):
            for entry in _achieves:
                if isinstance(entry, dict) and entry.get("i_d") == achieve_table_id:
                    for g in entry.get("season_achieve_group_info") or ():
                        if g.get("achieve_i_d") == req.condition_id:
                            reward_id = g.get("reward_i_d")
                            break
                    break

        if reward_id is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(MsgId.AbyssQuestRewardRsp, rsp, packet_id)
            return

        if not db.try_claim(
            session.player_id, "abyss_quest", f"{req.season_id}:{req.condition_id}"
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(MsgId.AbyssQuestRewardRsp, rsp, packet_id)
            return

        rsp.status = StatusCode.StatusCode_OK
        reward_list = resolve_reward(reward_id, _player_level(session.player_id))
        item_mgr.grant_items(
            session.player_id, reward_list, rsp_items=rsp.rewards, session=session
        )

        session.send(MsgId.AbyssQuestRewardRsp, rsp, packet_id)  # 2113,2114
