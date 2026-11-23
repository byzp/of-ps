from network.packet_handler import PacketHandler, packet_handler
from network.msg_id import MsgId

from proto.net_pb2 import (
    GetActivityBattlePassQuestRewardReq,
    GetActivityBattlePassQuestRewardRsp,
    StatusCode,
)
from utils.res_loader import res
import utils.db as db
import time
from utils.activity_state import template_id, bp_claim_key


def _quest_exp(bp_id, achieve_id):
    """任务经验查 BattlePass.battle_pass_queset.battle_pass_queset_item
    ({achieve_i_d, exp}); 优先在该战令的 day/week/season 任务组
    (battle_pass.day_quest_i_d/week_quest_i_d/season_quest_i_d)中找,
    找不到再全表兜底"""
    datas = res.get("BattlePass", {}).get("battle_pass_queset", {}).get("datas")
    if not isinstance(datas, (list, tuple)):
        return None
    groups = datas
    group_ids = None
    for e in res.get("BattlePass", {}).get("battle_pass", {}).get("datas") or ():
        if e.get("i_d") == template_id(bp_id):
            group_ids = {
                e.get("day_quest_i_d"),
                e.get("week_quest_i_d"),
                e.get("season_quest_i_d"),
            }
            break
    for only_own in (True, False):
        for g in groups:
            if only_own and group_ids is not None and g.get("i_d") not in group_ids:
                continue
            for item in g.get("battle_pass_queset_item", ()):
                if item.get("achieve_i_d") == achieve_id:
                    return item.get("exp", 0)
        if group_ids is None:
            break
    return None


@packet_handler(MsgId.GetActivityBattlePassQuestRewardReq)
class Handler(PacketHandler):
    def handle(self, session, data: bytes, packet_id: int):
        req = GetActivityBattlePassQuestRewardReq()
        req.ParseFromString(data)

        rsp = GetActivityBattlePassQuestRewardRsp()
        rsp.status = StatusCode.StatusCode_OK

        add_exp = _quest_exp(req.activity_battle_pass_id, req.achieve_id)
        if add_exp is None:
            rsp.status = StatusCode.StatusCode_CFG_NOT_FOUND
            session.send(
                MsgId.GetActivityBattlePassQuestRewardRsp, rsp, packet_id
            )  # 2135,2136
            return

        if not db.try_claim(
            session.player_id,
            "bp_quest_reward",
            bp_claim_key(req.activity_battle_pass_id, req.achieve_id),
        ):
            rsp.status = StatusCode.StatusCode_REPEAT_GET_REWARD
            session.send(
                MsgId.GetActivityBattlePassQuestRewardRsp, rsp, packet_id
            )  # 2135,2136
            return

        lv, total, cur = db.bp_add_exp(
            session.player_id, req.activity_battle_pass_id, add_exp
        )
        rsp.add_exp = add_exp
        rsp.current_lv = lv
        # 周经验按 ISO 周累计(kv ns=battle_pass_week)
        week_key = "exp:" + time.strftime("%G-W%V")
        rsp.current_week_exp = db.incr_kv(
            session.player_id, "battle_pass_week", week_key, add_exp
        )
        rsp.current_total_exp = total
        rsp.current_exp = cur

        session.send(
            MsgId.GetActivityBattlePassQuestRewardRsp, rsp, packet_id
        )  # 2135,2136
